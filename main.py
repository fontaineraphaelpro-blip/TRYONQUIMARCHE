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

# 🛑 ATTENTION : Les lignes fixes avec les clés sont supprimées ! 
# Elles seront lues automatiquement depuis les VARIABLES D'ENVIRONNEMENT de RENDER.

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
    # ⚠️ Mettez l'URL de votre frontend Netlify et l'URL de votre backend Render ici pour la sécurité
    allow_origins=["https://tryonia.netlify.app", "https://tryonquimarche-1.onrender.com"],
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

        # ⚠️ METTEZ L'URL NETLIFY ICI pour le retour de Stripe
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
    # La clé de sécurité peut rester en dur car elle est moins sensible que les clés API
    if request_data.security_key != "MOT_DE_PASSE_TRES_SECRET_A_METTRE_AUSSI_DANS_BUBBLE":
        raise HTTPException(status_code=403, detail="Clé de sécurité invalide.")

    try:
        # 1. Try-On (Replicate)
        output_vton = replicate.run(
            "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985",
            input={
                "human_img": request_data.person_image_url,
                "garm_img": request_data.clothing_image_url,
                "garment_des": "clothing",
                "category": request_data.category,
                "steps": 30, "crop": False, "seed": 42
            }
        )
        # Correction string
        raw_output = output_vton[0] if isinstance(output_vton, list) else output_vton
        raw_url = str(raw_output)

        # 2. Upscale (HD)
        try:
            output_upscale = replicate.run(
                "nightmareai/real-esrgan:42fed1c4974146d4d2414e2be2c5277c7fcf05fcc3a73ab415c72536722c5e08",
                input={"image": raw_url, "scale": 2, "face_enhance": True}
            )
            hd_output = output_upscale[0] if isinstance(output_upscale, list) else output_upscale
            final_url = str(hd_output)
        except Exception as e:
            print(f"Upscale échoué : {e}")
            final_url = raw_url

        # 3. Cloudinary
        upload = cloudinary.uploader.upload(final_url, folder="tryon_hd")
        return {"result_image_url": upload["secure_url"]}

    except Exception as e:
        print(f"❌ ERREUR : {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

# --- 5. SERVIR LE SITE WEB (Ces routes servent le frontend Netlify, gardez-les) ---

@app.get("/styles.css")
async def get_css(): return FileResponse("styles.css")

@app.get("/app.js")
async def get_js(): return FileResponse("app.js")

@app.get("/")
async def read_index(): return FileResponse("index.html")

# Le bloc uvicorn sera ignoré par Render, mais on le laisse pour les tests locaux
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3000)



