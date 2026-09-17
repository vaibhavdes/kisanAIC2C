export interface CropOption {
  id: string;
  label: string;
}

export interface CropCategory {
  category: string;
  crops: CropOption[];
}

export const MAHARASHTRA_CROPS: CropCategory[] = [
  {
    category: "Kharif Crops (खरीप पिके)",
    crops: [
      { id: "cotton", label: "🌿 Cotton (कापूस)" },
      { id: "soybean", label: "🌱 Soybean (सोयाबीन)" },
      { id: "pigeon_pea", label: "🫘 Pigeon Pea / Tur (तूर)" },
      { id: "sorghum", label: "🌾 Sorghum / Jowar (ज्वारी)" },
      { id: "pearl_millet", label: "🌾 Pearl Millet / Bajra (बाजरी)" },
      { id: "rice", label: "🌾 Rice / Paddy (भात)" },
      { id: "maize", label: "🌽 Maize (मका)" },
      { id: "groundnut", label: "🥜 Groundnut (भुईमूग)" },
      { id: "moong", label: "🌱 Green Gram / Moong (मूग)" },
      { id: "urad", label: "🫘 Black Gram / Urad (उडीद)" },
      { id: "sesame", label: "🌾 Sesame / Til (तीळ)" }
    ]
  },
  {
    category: "Rabi Crops (रब्बी पिके)",
    crops: [
      { id: "wheat", label: "🌾 Wheat (गहू)" },
      { id: "chickpea", label: "🧆 Chickpea / Harbara (हरभरा / चणा)" },
      { id: "rabi_sorghum", label: "🌾 Rabi Sorghum / Shalu (शाळू ज्वारी)" },
      { id: "mustard", label: "🌼 Mustard (मोहरी)" },
      { id: "safflower", label: "🌻 Safflower / Kardi (करडई)" }
    ]
  },
  {
    category: "Commercial, Spices & Horticulture (नगदी व फळबागा)",
    crops: [
      { id: "sugarcane", label: "🎋 Sugarcane (ऊस)" },
      { id: "onion", label: "🧅 Onion (कांदा)" },
      { id: "tomato", label: "🍅 Tomato (टोमॅटो)" },
      { id: "chilli", label: "🌶️ Chilli (मिरची)" },
      { id: "turmeric", label: "🟡 Turmeric (हळद)" },
      { id: "ginger", label: "🫚 Ginger (आले)" },
      { id: "pomegranate", label: "🍎 Pomegranate (डाळिंब)" },
      { id: "banana", label: "🍌 Banana (केळी)" },
      { id: "grapes", label: "🍇 Grapes (द्राक्षे)" },
      { id: "mango", label: "🥭 Mango (आंबा)" }
    ]
  }
];
