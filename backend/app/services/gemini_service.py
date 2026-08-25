import json
import logging
import re
import google.generativeai as genai
from backend.app.database import settings

logger = logging.getLogger(__name__)

# Configure Gemini if key is provided
if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)

def analyze_symptoms(symptoms: str) -> dict:
    """
    Analyzes symptoms using Gemini API.
    Returns: { "urgency_level": "...", "chief_complaint": "...", "suggested_questions": [...] }
    """
    fallback = {
        "urgency_level": "Medium",
        "chief_complaint": "Symptom reporting (AI analysis unavailable)",
        "suggested_questions": ["Please detail when your symptoms started.", "Have you experienced this before?"]
    }
    
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not configured. Using fallback symptom analysis.")
        return fallback

    prompt = f"""Analyse these patient symptoms.

Return ONLY valid JSON:

{{
  "urgency_level": "Low | Medium | High",
  "chief_complaint": "...",
  "suggested_questions": [
    "...",
    "...",
    "..."
  ]
}}

Do not provide a diagnosis.
Do not recommend medication.

Symptoms:
{symptoms}"""

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        # Set a short timeout equivalent or handle exceptions
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        
        text = response.text.strip()
        # Clean markdown codeblocks if returned
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        data = json.loads(text)
        
        # Validation
        urgency = data.get("urgency_level", "Medium")
        if urgency not in ["Low", "Medium", "High"]:
            urgency = "Medium"
            
        return {
            "urgency_level": urgency,
            "chief_complaint": data.get("chief_complaint", "Symptoms described by patient"),
            "suggested_questions": data.get("suggested_questions", fallback["suggested_questions"])
        }
    except Exception as e:
        logger.error(f"Gemini symptom analysis failed: {str(e)}")
        return fallback

def generate_post_visit_summary(clinical_notes: str, prescription: str) -> dict:
    """
    Generates post-visit patient-friendly summaries using Gemini.
    """
    fallback = {
        "patient_summary": f"Post-visit notes:\n{clinical_notes}\n\nPrescription:\n{prescription}",
        "medication_schedule": "Please follow the prescription as written by your doctor.",
        "follow_up_steps": "Please contact the clinic if you have any questions or if your condition worsens."
    }

    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not configured. Using fallback post-visit summary.")
        return fallback

    prompt = f"""Doctor notes: {clinical_notes}
Prescription: {prescription}

Generate:
- a patient-friendly explanation of their condition and treatment
- a detailed medication schedule based ONLY on the prescription
- clear follow-up steps

Do not invent information. Do not change the doctor's prescription. Do not provide a new diagnosis.

Return ONLY valid JSON:
{{
  "patient_summary": "...",
  "medication_schedule": "...",
  "follow_up_steps": "..."
}}"""

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        data = json.loads(text)
        return {
            "patient_summary": data.get("patient_summary", fallback["patient_summary"]),
            "medication_schedule": data.get("medication_schedule", fallback["medication_schedule"]),
            "follow_up_steps": data.get("follow_up_steps", fallback["follow_up_steps"])
        }
    except Exception as e:
        logger.error(f"Gemini post-visit summary generation failed: {str(e)}")
        return fallback
