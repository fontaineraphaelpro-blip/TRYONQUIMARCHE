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
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- 2. MODÈLES DE DONNÉES ---

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
    packs = {
        "pack_10": {"price_id": os.getenv("STRIPE_PRICE_ID_10"), "credits": 10},
        "pack_30": {"price_id": os.getenv("STRIPE_PRICE_ID_30"), "credits": 30},
        "pack_100": {"price_id": os.getenv("STRIPE_PRICE_ID_100"), "credits": 100},
    }

    if request_data.pack_id not in packs:
        raise HTTPException(status_code=400, detail="Pack ID invalide.")

    pack_info = packs[request_data.pack_id]
    
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


# --- 4. ROUTE AI (TRY-ON AVEC FLUX FILL REDUX) ---

@app.post("/api/v1/generate-tryon")
def generate_tryon(request_data: TryOnRequest):
    if request_data.security_key != "MOT_DE_PASSE_TRES_SECRET_A_METTRE_AUSSI_DANS_BUBBLE":
        raise HTTPException(status_code=403, detail="Clé de sécurité invalide.")

    try:
        print("🚀 Lancement de Flux-Fill-Redux Try-On...")

        # MAPPING DES CATÉGORIES
        # Votre frontend envoie "upper_body", "lower_body", "dresses"
        # Ce modèle attend "upper", "lower", "overall"
        cloth_type_mapped = "upper"
        if "lower" in request_data.category:
            cloth_type_mapped = "lower"
        elif "dress" in request_data.category or "overall" in request_data.category:
            cloth_type_mapped = "overall"

        # Appel au modèle cedoysch/flux-fill-redux-try-on
        # Pas de hf_token requis selon la doc de ce wrapper
        output_flux = replicate.run(
            "cedoysch/flux-fill-redux-try-on:cf5cb07a25e726fe2fac166a8c5ab52ddccd48657741670fb09d9954d4d8446f",
            input={
                "person_image": request_data.person_image_url,
                "cloth_image": request_data.clothing_image_url,
                "cloth_type": cloth_type_mapped,
                "output_quality": 100, # Qualité max pour le réalisme
                "output_format": "png"
            }
        )
        
        # Gestion de la sortie
        raw_output = output_flux[0] if isinstance(output_flux, list) else output_flux
        final_url = str(raw_output)
        
        print(f"✅ Génération terminée : {final_url}")

        # Upload vers Cloudinary
        upload = cloudinary.uploader.upload(final_url, folder="tryon_hd")
        
        return {"result_image_url": upload["secure_url"]}

    except Exception as e:
        print(f"❌ ERREUR REPLICATE : {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur IA: {str(e)}")


# --- 5. SERVIR LE SITE WEB ---

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
    if filename in ["main.py", "requirements.txt", "start.sh", ".env", ".gitignore"]:
        raise HTTPException(status_code=403, detail="Accès interdit")
    return get_static_file(filename)
