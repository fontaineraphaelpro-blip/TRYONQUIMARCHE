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
    category: str = "upper_body" # Valeurs attendues par OOT: 'upper_body', 'lower_body', 'dress'
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

    try:
        # --- 1. Lancement OOTDiffusion (SOTA Model) ---
        print(f"Lancement OOTDiffusion...")
        
        # Mapping des catégories pour OOTDiffusion
        # Le frontend envoie 'dresses', mais OOT attend souvent 'dress' (singulier)
        oot_category = request_data.category
        if oot_category == "dresses":
            oot_category = "dress"
            
        output_vton = replicate.run(
            "viktorfa/oot_diffusion:9f8fa4956970dde99689af7488157a30aa152e23953526a605df1d77598343d7",
            input={
                "model_image": request_data.person_image_url,  # ✅ Nom correct pour OOT
                "cloth_image": request_data.clothing_image_url, # ✅ Nom correct pour OOT
                "category": oot_category,                       # ✅ Ajout critique manquant dans ton code
                "steps": 20,       # 20 est optimal pour OOT
                "guidance_scale": 2,
                "seed": 42
            }
        )

        # 🛑 PROTECTION : Vérification du résultat
        if not output_vton or (isinstance(output_vton, list) and len(output_vton) == 0):
            print("❌ OOTDiffusion a échoué (Liste vide).")
            raise Exception("L'IA n'a pas réussi à générer l'image. (Vérifiez le cadrage photo).")

        # Récupération de l'URL
        if isinstance(output_vton, list):
            final_url = str(output_vton[0])
        else:
            final_url = str(output_vton)

        # --- 2. Cloudinary (Direct, Upscale retiré pour stabilité) ---
        print(f"Succès IA. Upload vers Cloudinary...")
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
