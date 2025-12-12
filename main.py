import os
import replicate
import cloudinary
import cloudinary.uploader
import stripe
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- 1. CONFIGURATION ---

# Lecture des clés depuis les variables d'environnement Render
os.environ["REPLICATE_API_TOKEN"] = os.getenv("REPLICATE_API_TOKEN")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

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
            line_items=[{'price': pack_info["price_id"], 'quantity': 1}],
            mode='payment',
            success_url=success_url_with_credits,
            cancel_url=request_data.cancel_url,
        )
        return {"url": checkout_session.url}
    except Exception as e:
        print(f"Erreur Stripe: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 4. ROUTE AI (OOTDiffusion) ---

@app.post("/api/v1/generate-tryon")
def generate_tryon(request_data: TryOnRequest):
    if request_data.security_key != "MOT_DE_PASSE_TRES_SECRET_A_METTRE_AUSSI_DANS_BUBBLE":
        raise HTTPException(status_code=403, detail="Clé de sécurité invalide.")

    try:
        print("🚀 Lancement de OOTDiffusion (viktorfa)...")

        # Utilisation du modèle OOTDiffusion demandé
        # Note : Ce modèle est excellent pour le "fitting" naturel
        output_ootd = replicate.run(
            "viktorfa/oot_diffusion:9f8fa4956970dde99689af7488157a30aa152e23953526a605df1d77598343d7",
            input={
                "model_image": request_data.person_image_url,
                "garment_image": request_data.clothing_image_url,
                "steps": 20,       # 20 est le réglage standard (rapide et propre)
                "guidance_scale": 2,
                "seed": 42
            }
        )
        
        # Gestion de la sortie (OOTD renvoie souvent une liste)
        raw_output = output_ootd[0] if isinstance(output_ootd, list) else output_ootd
        final_url = str(raw_output)
        
        print(f"✅ Génération terminée : {final_url}")

        upload = cloudinary.uploader.upload(final_url, folder="tryon_hd")
        return {"result_image_url": upload["secure_url"]}

    except Exception as e:
        print(f"❌ ERREUR IA : {str(e)}")
        # Si vous voyez une erreur ici, vérifiez les logs Render
        raise HTTPException(status_code=500, detail=f"Erreur modèle IA: {str(e)}")

# --- 5. FICHIERS STATIQUES ---

def get_static_file(filename: str):
    file_path = os.path.join(os.getcwd(), filename)
    if os.path.exists(file_path):
        media_type = "application/javascript" if filename.endswith(".js") else "text/css" if filename.endswith(".css") else None
        return FileResponse(file_path, media_type=media_type)
    raise HTTPException(status_code=404, detail="Fichier non trouvé")

@app.get("/")
def read_root(): return get_static_file("index.html")

@app.get("/{filename}")
def read_file(filename: str):
    if filename in ["main.py", "requirements.txt", "start.sh", ".env", ".gitignore"]:
        raise HTTPException(status_code=403, detail="Accès interdit")
    return get_static_file(filename)
