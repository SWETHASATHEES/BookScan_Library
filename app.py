
import json
import re

import requests
import streamlit as st
from google import genai
from PIL import Image

# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="Library Book Cataloging Assistant",
    page_icon="📚",
    layout="centered",
)

# --------------------------------------------------
# SECRETS & API SETUP
# --------------------------------------------------
from google import genai

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=GEMINI_API_KEY.strip())


# --------------------------------------------------
# GEMINI BOOK DETAILS EXTRACTION
# --------------------------------------------------

def extract_book_details(image):
    prompt = """
    Examine the uploaded book cover, title page, or copyright page.

    Extract these fields:
    1. title
    2. author
    3. publisher
    4. language: Malayalam, English, or Bilingual
    5. category
    6. price
    7. edition
    8. subjects: brief comma-separated keywords

    IMPORTANT:
    - Preserve Malayalam titles and author names in Malayalam script.
    - Do not translate Malayalam names into English.
    - Do not invent missing information.
    - Use an empty string for information that is not visible.
    - Return only a valid JSON object with these exact keys:
      title, author, publisher, language, category, price,
      edition, subjects.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, image],
            config={
                "response_mime_type": "application/json"
            },
        )

        if not response.text:
            raise ValueError("Gemini returned an empty response.")

        text = response.text.strip()

        # Remove Markdown code fences if present.
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        data = json.loads(text)

        keys = [
            "title",
            "author",
            "publisher",
            "language",
            "category",
            "price",
            "edition",
            "subjects",
        ]

        return {
            key: str(data.get(key, "") or "")
            for key in keys
        }

    except json.JSONDecodeError as e:
        raise ValueError(
            "Gemini returned invalid JSON. Please try another image."
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"Book detail extraction failed: {e}"
        ) from e

# --------------------------------------------------
# SAVE TO GOOGLE SHEETS THROUGH APPS SCRIPT
# --------------------------------------------------
def save_to_google_sheet(row):
    payload = {"row": row}

    response = requests.post(
        APPS_SCRIPT_URL,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(
            "Apps Script did not return JSON. Check the deployment "
            "URL and ensure the web app is deployed correctly."
        )

    if not result.get("success", False):
        raise RuntimeError(
            result.get("error", "Apps Script could not save the record.")
        )

    return result


# --------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------
st.title("📚 Library Book Cataloging Assistant")

st.write(
    "Upload a book image or take a photo. Review the extracted "
    "details before saving them to your library spreadsheet."
)

st.subheader("1. Choose an image source")

image_source = st.radio(
    "How would you like to add the book image?",
    ["Upload Image", "Use Camera"],
    horizontal=True,
)

image = None

if image_source == "Upload Image":
    image_file = st.file_uploader(
        "Upload a book cover or title page",
        type=["jpg", "jpeg", "png"],
        key="book_upload",
    )

    if image_file is not None:
        image = Image.open(image_file).convert("RGB")

else:
    camera_file = st.camera_input(
        "Take a photo of the book cover or title page",
        key="book_camera",
    )

    if camera_file is not None:
        image = Image.open(camera_file).convert("RGB")

if image is not None:
    st.image(
        image,
        caption="Book image",
        use_container_width=True,
    )

    if st.button("Extract Book Details", type="primary"):
        with st.spinner(
            "Recognizing Malayalam and English text..."
        ):
            try:
                data = extract_book_details(image)
                st.session_state["extracted_data"] = data
                st.session_state.pop("saved_record", None)
                st.success(
                    "Extraction complete. Review the details below."
                )
            except Exception as e:
                st.error(f"Extraction failed: {e}")


# --------------------------------------------------
# REVIEW, EDIT & SAVE
# --------------------------------------------------
if "extracted_data" in st.session_state:
    data = st.session_state["extracted_data"]

    st.subheader("2. Review and complete book details")

    with st.form("book_form"):
        col1, col2 = st.columns(2)

        with col1:
            stock_number = st.text_input("Stock Number")
            call_number = st.text_input("Call Number")
            title = st.text_input(
                "Title", value=data.get("title", "")
            )
            author = st.text_input(
                "Author", value=data.get("author", "")
            )

            language_options = [
                "Malayalam", "English", "Bilingual"
            ]
            detected_language = data.get("language", "")
            language_index = (
                language_options.index(detected_language)
                if detected_language in language_options
                else 0
            )

            language = st.selectbox(
                "Language",
                language_options,
                index=language_index,
            )

            category = st.text_input(
                "Category", value=data.get("category", "")
            )
            price = st.text_input(
                "Price", value=data.get("price", "")
            )

        with col2:
            publisher = st.text_input(
                "Publisher", value=data.get("publisher", "")
            )
            edition = st.text_input(
                "Edition", value=data.get("edition", "")
            )
            shelf = st.text_input("Shelf")
            barcode = st.text_input("Barcode")

            booktype = st.selectbox(
                "Book Type",
                ["Reference", "Circulating", "Textbook", "Rare"],
            )

            status = st.selectbox(
                "Status",
                ["Available", "Issued", "Processing", "Damaged"],
            )

            subjects = st.text_input(
                "Subjects", value=data.get("subjects", "")
            )

        submitted = st.form_submit_button(
            "Save to Google Sheets",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not title.strip():
            st.error("Please enter the book title before saving.")
        else:
            # Preserve the original A:N column order.
            row = [
                stock_number,
                call_number,
                title,
                author,
                language,
                category,
                price,
                publisher,
                edition,
                shelf,
                barcode,
                booktype,
                status,
                subjects,
            ]

            try:
                with st.spinner("Saving book record..."):
                    result = save_to_google_sheet(row)

                st.session_state["saved_record"] = True
                st.session_state.pop("extracted_data", None)

                st.success(
                    result.get(
                        "message",
                        "Book record saved successfully!"
                    )
                )

            except Exception as e:
                st.error(f"Could not save the book record: {e}")

if st.session_state.get("saved_record"):
    st.success("You can now add the next book.")
    if st.button("Add Another Book"):
        st.session_state.pop("saved_record", None)
        st.rerun()
