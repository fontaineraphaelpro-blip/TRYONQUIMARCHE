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
    allow_origins=["https://tryonia.netlify.app", "https://tryonquimarche.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 2. MODÈLES ---
class TryOnRequest(BaseModel):
    person_image_url: str
    clothing_image_url: str
    category: str = "upper_body"
    user_id: str
    security_key: str

class PaymentRequest(BaseModel):
    pack_id: str

# --- 3. PACKS ---
PACKS = {
    "pack_10": {"name": "10 Crédits IA", "amount": 499, "credits": 10},
    "pack_30": {"name": "30 Crédits IA", "amount": 999, "credits": 30},
    "pack_100": {"name": "100 Crédits IA", "amount": 1999, "credits": 100}
}

# --- 4. ROUTES API ---

@app.post("/api/v1/create-checkout-session")
def create_checkout_session(request: PaymentRequest):
    try:
        pack = PACKS.get(request.pack_id)
        if not pack:
            raise HTTPException(status_code=400, detail="Pack inconnu")

        YOUR_DOMAIN = "https://tryonia.netlify.app"
        success_url = f"{YOUR_DOMAIN}/?success=true&add_credits={pack['credits']}"

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {'name': pack['name']},
                    'unit_amount': pack['amount'],
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=YOUR_DOMAIN + '/?canceled=true',
        )
        return {"url": checkout_session.url}
    except Exception as e:
        print(f"Erreur Stripe : {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/generate-tryon")
def generate_tryon(request_data: TryOnRequest):
    if request_data.security_key != "MOT_DE_PASSE_TRES_SECRET_A_METTRE_AUSSI_DANS_BUBBLE":
        raise HTTPException(status_code=403, detail="Clé de sécurité invalide.")

    # ✨ PROMPT AMÉLIORÉ : C'est ici que se joue le réalisme
    # On ajoute des mots clés pour la texture et la lumière
    REALISTIC_PROMPT = "photorealistic, high quality, highly detailed, realistic texture, 4k, studio lighting, raw photo, vivid colors"

    try:
        # 1. Try-On (Replicate)
        print("Lancement Replicate avec images :")
        print(f"Humain: {request_data.person_image_url}")
        print(f"Vêtement: {request_data.clothing_image_url}")

        output_vton = replicate.run(
            "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985",
            input={
                "human_img": request_data.person_image_url,
                "garm_img": request_data.clothing_image_url,
                "garment_des": REALISTIC_PROMPT, # ✅ Utilisation du prompt riche
                "category": request_data.category,
                "steps": 40, 
                "crop": False, # ✅ On garde le crop pour éviter l'écrasement
                "seed": 42# "seed": 42  <-- ❌ J'ai retiré le seed pour avoir des variations plus naturelles
            }
        )

        # 🛑 PROTECTION CRITIQUE
        if not output_vton or (isinstance(output_vton, list) and len(output_vton) == 0):
            print("❌ Replicate a retourné une liste vide (FAILED).")
            raise Exception("L'IA a échoué (Status FAILED). Vérifiez que la photo contient bien une personne visible.")

        # Récupération sécurisée
        if isinstance(output_vton, list):
            final_url = str(output_vton[0])
        else:
            final_url = str(output_vton)

        # 2. Cloudinary (Direct)
        print(f"Succès Replicate. Upload vers Cloudinary...")
        upload = cloudinary.uploader.upload(final_url, folder="tryon_hd")
        
        return {"result_image_url": upload["secure_url"]}

    except Exception as e:
        print(f"❌ ERREUR GENERALE : {str(e)}")
        raise HTTPException(status_code=500, detail=f"Echec IA: {str(e)}")

# --- 5. SERVIR LE SITE WEB ---

@app.get("/styles.css")
async def get_css(): return FileResponse("styles.css")

@app.get("/app.js")
async def get_js(): return FileResponse("app.js")

@app.get("/")
async def read_index(): return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)

