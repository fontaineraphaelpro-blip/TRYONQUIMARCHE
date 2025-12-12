import os
import replicate
import cloudinary
import cloudinary.uploader
import stripe
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- 1. CONFIGURATION (VARIABLES D'ENVIRONNEMENT RENDER) ---

# Replicate lit directement la variable d'environnement (REPLICATE_API_TOKEN)
os.environ["REPLICATE_API_TOKEN"] = os.getenv("REPLICATE_API_TOKEN")

# Stripe lit la clé secrète depuis l'environnement
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Cloudinary lit les identifiants depuis l'environnement
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET")
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # Autorise tout le monde (Netlify, Localhost)
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- 2. MODÈLES DE DONNÉES ---

class TryOnRequest(BaseModel):
    person_image_url: str
    clothing_image_url: str
    category: str # Note: Flux gère souvent la catégorie automatiquement, mais on garde le champ
    user_id: str
    security_key: str

class CheckoutRequest(BaseModel):
    pack_id: str
    success_url: str
    cancel_url: str


# --- 3. ROUTES STRIPE (PAIEMENT) ---

@app.post("/api/v1/create-checkout-session")
def create_checkout_session(request_data: CheckoutRequest):
    # Configuration des packs
    packs = {
        "pack_10": {"price_id": os.getenv("STRIPE_PRICE_ID_10"), "credits": 10},
        "pack_30": {"price_id": os.getenv("STRIPE_PRICE_ID_30"), "credits": 30},
        "pack_100": {"price_id": os.getenv("STRIPE_PRICE_ID_100"), "credits": 100},
    }

    if request_data.pack_id not in packs:
        raise HTTPException(status_code=400, detail="Pack ID invalide.")

    pack_info = packs[request_data.pack_id]
    
    # Construction de l'URL de succès
    success_url_with_credits = f"{request_data.success_url}?success=true&add_credits={pack_info['credits']}"

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': pack_info["price_id"],
                    'quantity': 1,
                },
            ],
            mode='payment',
            success_url=success_url_with_credits,
            cancel_url=request_data.cancel_url,
        )
        return {"url": checkout_session.url}
    except Exception as e:
        print(f"Erreur Stripe: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- 4. ROUTE AI (TRY-ON AVEC CatVTON-Flux) ---

@app.post("/api/v1/generate-tryon")
def generate_tryon(request_data: TryOnRequest):
    # Vérification de sécurité
    if request_data.security_key != "MOT_DE_PASSE_TRES_SECRET_A_METTRE_AUSSI_DANS_BUBBLE":
        raise HTTPException(status_code=403, detail="Clé de sécurité invalide.")

    try:
        print("🚀 Lancement de CatVTON-Flux...")

        # Appel au modèle mmezhov/catvton-flux
        output_flux = replicate.run(
            "mmezhov/catvton-flux:cc41d1b963023987ed2ddf26e9264efcc96ee076640115c303f95b0010f6a958",
            input={
                "image": request_data.person_image_url,     # L'image de la personne
                "garment": request_data.clothing_image_url, # L'image du vêtement
                "num_steps": 30,       # 30 étapes : bon équilibre qualité/vitesse pour Flux
                "guidance_scale": 3.5, # Réglage recommandé pour le réalisme
                "seed": 42,
                "width": 768,          # Résolution standard Flux (Portrait)
                "height": 1024
            }
        )
        
        # Gestion du format de réponse de Replicate (parfois liste, parfois objet)
        raw_output = output_flux[0] if isinstance(output_flux, list) else output_flux
        final_url = str(raw_output)
        
        print(f"✅ Génération terminée par Replicate : {final_url}")

        # Upload vers Cloudinary pour stocker le résultat de manière fiable
        upload = cloudinary.uploader.upload(final_url, folder="tryon_hd")
        
        return {"result_image_url": upload["secure_url"]}

    except Exception as e:
        print(f"❌ ERREUR REPLICATE/CLOUDINARY : {str(e)}")
        # Astuce : Regardez les logs Render si une erreur 500 apparaît
        raise HTTPException(status_code=500, detail=f"Erreur IA: {str(e)}")


# --- 5. SERVIR LE SITE WEB (FICHIERS STATIQUES) ---

def get_static_file(filename: str):
    file_path = os.path.join(os.getcwd(), filename)
    if os.path.exists(file_path):
        if filename.endswith(".js"):
            media_type = "application/javascript"
        elif filename.endswith(".css"):
            media_type = "text/css"
        else:
            media_type = None
        return FileResponse(file_path, media_type=media_type)
    raise HTTPException(status_code=404, detail="Fichier non trouvé")

@app.get("/")
def read_root():
    return get_static_file("index.html")

@app.get("/{filename}")
def read_file(filename: str):
    # Sécurité : on empêche de lire le code source python ou les envs
    if filename in ["main.py", "requirements.txt", "start.sh", ".env", ".gitignore"]:
        raise HTTPException(status_code=403, detail="Accès interdit")
    return get_static_file(filename)
