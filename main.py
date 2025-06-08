from fastapi import FastAPI, HTTPException
import requests
import fitz  
import os
import re
from dotenv import load_dotenv  
import json
import uvicorn
load_dotenv()

app = FastAPI()

S3_CV_URL = "https://mylatestcv.s3.ap-south-1.amazonaws.com/Naman_Kansal.pdf"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
)

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from PDF bytes using PyMuPDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text("text") + "\n"
    return text.strip()

def call_gemini_api(prompt_text: str) -> dict:
    """Call Gemini 2.5 Flash API with given prompt text."""
    headers = {
        "Content-Type": "application/json",
    }
    params = {"key": GEMINI_API_KEY}
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt_text
                    }
                ]
            }
        ]
    }
    response = requests.post(GEMINI_API_URL, headers=headers, params=params, json=body)
    if response.status_code != 200:
        raise Exception(f"Gemini API error {response.status_code}: {response.text}")
    return response.json()

def remove_nulls(data):
    if isinstance(data, dict):
        return {k: remove_nulls(v) for k, v in data.items() if v is not None}
    elif isinstance(data, list):
        return [remove_nulls(item) for item in data if item is not None]
    else:
        return data


@app.get("/parse-resume")
def parse_resume():
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    # Step 1: Download PDF from S3
    res = requests.get(S3_CV_URL)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to download resume from S3")

    # Step 2: Extract text from PDF
    pdf_bytes = res.content
    extracted_text = extract_text_from_pdf(pdf_bytes)
    if not extracted_text.strip():
        raise HTTPException(status_code=500, detail="No text extracted from PDF")

    # Step 3: Prepare prompt for Gemini
    prompt = (
        "Extract structured resume information in JSON format from the following resume text.\n"
        "Return JSON with fields: name, contact (email, phone, linkedin), education, skills, "
        "achievements, experience (company, title, duration, location, description), projects.\n\n"
        f"Resume Text:\n{extracted_text}\n\nJSON Output:"
    )

    # Step 4: Call Gemini API
    try:
        gemini_response = call_gemini_api(prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini API error: {str(e)}")

    # Step 5: Extract and clean JSON string from Gemini response
    # Step 5: Extract and clean JSON string from Gemini response
    try:
    # Get the raw text from the first candidate content
        raw_text = gemini_response["candidates"][0]["content"]["parts"][0]["text"]

        if isinstance(raw_text, dict):
            parsed_resume = raw_text
        else:
    # It's string, so remove markdown and parse JSON
            clean_json_str = re.sub(r"^```json\s*|```$", "", raw_text, flags=re.DOTALL).strip()
            parsed_resume = json.loads(clean_json_str)

    

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse Gemini response JSON: {str(e)}")

    # Step 6: Clean up the parsed resume data
    parsed_resume = remove_nulls(parsed_resume)
    return {"parsed_resume": parsed_resume}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
