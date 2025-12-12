import os
import replicate
import cloudinary
import cloudinary.uploader
import stripe
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- 1. CONFIGURATION (MISE À JOUR POUR RENDER) ---

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
    # ⚠️ Mettez l'URL de votre frontend Netlify et l'URL de votre backend Render ici
    # Exemple : ["https://tryonia.netlify.app", "https://tryonquimarche-1.onrender.com"]
    allow_origins=["*"], # On laisse le wildcard pour la flexibilité sur Render/Netlify
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- 2. MODÈLES DE DONNÉES Pydantic ---

class TryOnRequest(BaseModel):
    person_image_url: str
    clothing_image_url: str
    category: str
    user_id: str
    security_key: str

class CheckoutRequest(BaseModel):
    pack_id: str
    success_url: str
    cancel_url: str


# --- 3. ROUTES STRIPE ---

@app.post("/api/v1/create-checkout-session")
def create_checkout_session(request_data: CheckoutRequest):
    # Les prix et les crédits correspondent à ce qui a été défini sur Stripe
    packs = {
        "pack_10": {"price_id": os.getenv("STRIPE_PRICE_ID_10"), "credits": 10},
        "pack_30": {"price_id": os.getenv("STRIPE_PRICE_ID_30"), "credits": 30},
        "pack_100": {"price_id": os.getenv("STRIPE_PRICE_ID_100"), "credits": 100},
    }

    if request_data.pack_id not in packs:
        raise HTTPException(status_code=400, detail="Pack ID invalide.")

    pack_info = packs[request_data.pack_id]
    
    # Ajout d'un paramètre de succès pour mettre à jour les crédits côté client
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


# --- 4. ROUTE AI (TRY-ON) OPTIMISÉE POUR LE RÉALISME ---

@app.post("/api/v1/generate-tryon")
def generate_tryon(request_data: TryOnRequest):
    # Clé de sécurité à vérifier avec le frontend
    if request_data.security_key != "MOT_DE_PASSE_TRES_SECRET_A_METTRE_AUSSI_DANS_BUBBLE":
        raise HTTPException(status_code=403, detail="Clé de sécurité invalide.")

    # --- PROMPT HYPER RÉALISTE POUR LE VTON ---
    REALISTIC_PROMPT = "photorealistic, perfectly fitted, highly detailed, sharp focus, professional studio lighting, high quality, 8k"

    try:
        # 1. Try-On (Replicate) avec 75 étapes
        output_vton = replicate.run(
            "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985",
            input={
                "human_img": request_data.person_image_url,
                "garm_img": request_data.clothing_image_url,
                # Utilisation du prompt réaliste
                "garment_des": REALISTIC_PROMPT, 
                "category": request_data.category,
                # Augmentation des étapes pour une meilleure qualité (COÛT PLUS ÉLEVÉ)
                "steps": 40, 
                "crop": False, 
                "seed": 42
            }
        )
        
        # Récupération de l'URL brute du résultat VTON
        raw_output = output_vton[0] if isinstance(output_vton, list) else output_vton
        final_url = str(raw_output)

        # ⚠️ ÉTAPE UPSCALE RETIRÉE.
        
        # 2. Cloudinary (On uploade le résultat VTON directement)
        upload = cloudinary.uploader.upload(final_url, folder="tryon_hd")
        return {"result_image_url": upload["secure_url"]}

    except Exception as e:
        print(f"❌ ERREUR : {str(e)}")
        # NOTE : Si vous voyez cette erreur dans Render, vérifiez immédiatement REPLICATE_API_TOKEN.
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


# --- 5. SERVIR LE SITE WEB (Ces routes servent le frontend) ---

# Fonction pour servir les fichiers statiques (index.html, styles.css, app.js, etc.)
def get_static_file(filename: str):
    # Tente de servir le fichier depuis le répertoire racine
    file_path = os.path.join(os.getcwd(), filename)
    if os.path.exists(file_path):
        # Détermine le type MIME (utile pour les navigateurs)
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
    # Empêche l'accès aux fichiers sensibles ou non statiques
    if filename in ["main.py", "requirements.txt", "start.sh", ".env"]:
        raise HTTPException(status_code=403, detail="Accès interdit")
    return get_static_file(filename)

