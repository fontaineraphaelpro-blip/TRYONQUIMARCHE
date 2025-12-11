// --- 1. CONFIGURATION ---
const BASE_URL = 'https://tryonquimarche-1.onrender.com';

const API_ENDPOINT = `${BASE_URL}/api/v1/generate-tryon`;
const PAYMENT_ENDPOINT = `${BASE_URL}/api/v1/create-checkout-session`;

// CLÉS
const SECURITY_KEY = 'MOT_DE_PASSE_TRES_SECRET_A_METTRE_AUSSI_DANS_BUBBLE';
// Ces variables ne sont plus utilisées dans la fonction d'upload, mais on les garde pour référence.
const CLOUDINARY_CLOUD_NAME = 'dbhxjrj8c'; 
const CLOUDINARY_UPLOAD_PRESET = 'tryon_upload'; 

// ⚠️ L'URL de Cloudinary est ici définie en DUR pour contourner tout bug de variable.
const CLOUDINARY_FETCH_URL = 'https://api.cloudinary.com/v1_1/dbhxjrj8c/image/upload';


// --- 2. GESTION CRÉDITS ---
// J'ai remis 50 crédits pour faciliter votre test
let credits = parseInt(localStorage.getItem('credits') || '50');

window.onload = function() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('success') === 'true') {
        const added = parseInt(urlParams.get('add_credits') || '0');
        if (added > 0) {
            credits += added;
            localStorage.setItem('credits', credits);
            alert(`🎉 Merci ! ${added} crédits ont été ajoutés.`);
        }
        window.history.replaceState({}, document.title, "/");
    }
    updateUI();
};

function updateUI() {
    const creditsSpan = document.getElementById('creditsLeft');
    creditsSpan.innerText = credits;
    if (credits <= 0) creditsSpan.style.color = "red";
    else creditsSpan.style.color = "#6366f1";
}

// GESTION MODALE
function openPricing() { document.getElementById('pricingModal').style.display = 'flex'; }
function closePricing() { document.getElementById('pricingModal').style.display = 'none'; }

// PAIEMENT
async function buyPack(packId) {
    try {
        const response = await fetch(PAYMENT_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pack_id: packId }) 
        });
        const data = await response.json();
        if(data.url) window.location.href = data.url; 
        else alert("Erreur : " + (data.detail || "Problème serveur"));
    } catch (e) {
        console.error(e);
        alert("Impossible de contacter le serveur.");
    }
}

// UTILITAIRES
function previewImage(inputId, previewId, placeholderId) {
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    const placeholder = document.getElementById(placeholderId);
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            preview.src = e.target.result;
            preview.style.display = 'block';
            if (placeholder) placeholder.style.display = 'none';
        };
        reader.readAsDataURL(input.files[0]);
    }
}

// ⚠️ FONCTION D'UPLOAD AVEC VALEURS EN DUR
async function uploadToCloudinary(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    // Paramètres en DUR
    formData.append('upload_preset', 'tryon_upload'); 
    formData.append('cloud_name', 'dbhxjrj8c'); 

    try {
        // Utilisation de l'URL fixe
        const response = await fetch(CLOUDINARY_FETCH_URL, { method: 'POST', body: formData });
        const data = await response.json();

        if (!response.ok) {
             throw new Error(data.error?.message || "Erreur upload Cloudinary. (Vérifiez votre Preset 'ml_default'!)");
        }
        return data.secure_url;
    } catch (error) { 
        throw new Error("Erreur Cloudinary : " + error.message); 
    }
}

// START TRYON
async function startTryOn() {
    if (credits <= 0) { openPricing(); return; }

    const userFile = document.getElementById('userImage').files[0];
    const clothingFile = document.getElementById('clothingImage').files[0];
    const loadingMessage = document.getElementById('loadingMessage');
    const generateButton = document.getElementById('generateButton');
    const resultImg = document.getElementById('resultImage');
    const resultPlaceholder = document.getElementById('resultPlaceholder');

    if (!userFile || !clothingFile) { alert("Veuillez choisir les deux images !"); return; }

    credits--;
    localStorage.setItem('credits', credits);
    updateUI();

    loadingMessage.style.display = 'flex';
    generateButton.disabled = true;
    resultImg.style.display = 'none';
    if(resultPlaceholder) resultPlaceholder.style.display = 'block';

    try {
        const [userImageUrl, clothingImageUrl] = await Promise.all([
            uploadToCloudinary(userFile),
            uploadToCloudinary(clothingFile)
        ]);
        const selectedCategory = document.getElementById('categorySelect').value;

        const response = await fetch(API_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                person_image_url: userImageUrl,
                clothing_image_url: clothingImageUrl,
                category: selectedCategory,
                user_id: 'user_' + Date.now(),
                security_key: SECURITY_KEY
            })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Erreur API Backend");

        resultImg.src = data.result_image_url;
        resultImg.style.display = 'block';
        if(resultPlaceholder) resultPlaceholder.style.display = 'none';
        const downloadBtn = document.getElementById('downloadLink');
        downloadBtn.href = data.result_image_url;
        downloadBtn.style.display = 'inline-flex';

    } catch (error) {
        console.error(error); alert("Erreur : " + error.message);
        credits++; localStorage.setItem('credits', credits); updateUI();
    } finally {
        loadingMessage.style.display = 'none';
        generateButton.disabled = false;
    }
}

// --- SECURITÉ FERMETURE ---
window.onclick = function(event) {
    const modal = document.getElementById('pricingModal');
    if (event.target == modal) closePricing();
}
window.ontouchstart = function(event) {
    const modal = document.getElementById('pricingModal');
    if (event.target == modal) closePricing();
}
