import streamlit as st
import requests
import uuid

# --- Configuration ---
# Define the URL for your n8n webhook
N8N_WEBHOOK_URL = "https://yeetus.app.n8n.cloud/webhook-test/a75a0002-e2d1-418b-8ce7-17e60a61d872"
BEARER_TOKEN = "da118d064e7392bfe017c56fcf4def9119d144f8803e6932978210e20ed5306a" # Replace with your actual token
DOC_ANALYSIS_WEBHOOK_URL = "https://yeetus.app.n8n.cloud/webhook-test/3320a9f9-0023-4a62-b29b-f3d49d70d634" # Add your new n8n webhook URL

st.title("InvestAgent MVP")

# --- Document Analysis UI ---
st.subheader("1. Analyze Documents")
uploaded_files = st.file_uploader(
    "Upload one or more project whitepapers (PDF only)",
    type="pdf",
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("Analyze Documents"):
        # Use a status container to show progress
        status = st.status(f"Starting analysis for {len(uploaded_files)} document(s)...", expanded=True)
        try:
            for i, uploaded_file in enumerate(uploaded_files):
                status.write(f"Analyzing '{uploaded_file.name}' ({i+1}/{len(uploaded_files)})...")
                
                # We send each file as multipart-form data
                files = {'file': (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                payload = {'sessionId': st.session_state.sessionId}
                headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}

                # This call now waits for the entire n8n workflow to finish
                response = requests.post(DOC_ANALYSIS_WEBHOOK_URL, data=payload, files=files, headers=headers)
                response.raise_for_status()
                
                # Get the JSON response from the "Respond to Webhook" node
                backend_response = response.json()
                
                # Display the message from the backend, with a fallback
                response_message = backend_response.get("message", f"Finished '{uploaded_file.name}'")
                status.write(f"✅ {response_message}")

            status.update(label="Analysis complete!", state="complete", expanded=False)
            st.success(f"Successfully analyzed {len(uploaded_files)} document(s). You can now ask questions below.")

        except requests.exceptions.RequestException as e:
            status.update(label="Analysis failed!", state="error")
            st.error(f"Error processing document: {e}")
        except Exception as e:
            status.update(label="Analysis failed!", state="error")
            st.error(f"An unexpected error occurred: {e}")

# --- Session Management ---
# Initialize sessionId in session_state if it doesn't exist
if 'sessionId' not in st.session_state:
    st.session_state.sessionId = str(uuid.uuid4())

# --- UI and Backend Call ---
st.subheader("2. Ask a Question")
# Input box for the user's chat input
user_chat_input = st.text_input("Ask a question about your uploaded document or a crypto project:")

if st.button("Send"):
    if user_chat_input:
        st.info("Sending chat input to backend...")
        try:
            # --- Prepare the request ---
            headers = {
                "Authorization": f"Bearer {BEARER_TOKEN}"
            }
            payload = {
                "chatInput": user_chat_input,
                "sessionId": st.session_state.sessionId
            }

            # Send the user's chat input to the n8n webhook
            response = requests.post(N8N_WEBHOOK_URL, json=payload, headers=headers)
            response.raise_for_status() # Raise an exception for bad status codes

            # Display the response from n8n
            backend_response = response.json()
            st.success("Response from AI Agent:")
            st.json(backend_response)

        except requests.exceptions.RequestException as e:
            st.error(f"Error connecting to backend: {e}")
    else:
        st.warning("Please enter a question.") 