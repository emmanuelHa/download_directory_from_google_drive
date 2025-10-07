import io
import os
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- CONFIGURATION ---
# The folder ID from your Google Drive URL (e.g., .../folders/THIS_IS_THE_ID)
TARGET_FOLDER_ID = '1oe5rSJU0eNEvFTxTZqt0MR8AiMD7KaDF'
# The local path where the folder structure will be created
DOWNLOAD_BASE_PATH = './Downloaded_Drive_Content'
# Drive API access scope (read-only is sufficient for downloading)
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
# --- END CONFIGURATION ---

def authenticate():
    """Handles OAuth2 authentication flow for Google Drive API."""
    creds = None
    TOKEN_FILE = 'token.json'
    CREDENTIALS_FILE = 'credentials.json'

    # Load saved credentials if they exist
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # If credentials are not valid or don't exist, start the flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("Starting authentication flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the new credentials
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def download_file(drive_service, file_id, file_name, save_path):
    """Downloads a single file, handling native Google Workspace formats."""
    try:
        file_path = os.path.join(save_path, file_name)
        
        # Get metadata to check mime type
        file_metadata = drive_service.files().get(fileId=file_id, fields='mimeType').execute()
        mime_type = file_metadata.get('mimeType')
        request = None
        export_format = None

        # Check for native Google Workspace files (Docs, Sheets, Slides, etc.)
        if mime_type.startswith('application/vnd.google-apps'):
            if 'document' in mime_type:
                export_format = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' # .docx
                file_path += '.docx'
            elif 'spreadsheet' in mime_type:
                export_format = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' # .xlsx
                file_path += '.xlsx'
            elif 'presentation' in mime_type:
                export_format = 'application/vnd.openxmlformats-officedocument.presentationml.presentation' # .pptx
                file_path += '.pptx'
            elif 'drawing' in mime_type:
                export_format = 'image/png' # .png
                file_path += '.png'
            else:
                print(f"  ⚠️ Skipping unhandled native Google file: {file_name}")
                return

            # Use files().export_media() for native types
            request = drive_service.files().export_media(fileId=file_id, mimeType=export_format)
            print(f"  ⬇️ Exporting {file_name} as {os.path.basename(file_path)}")
        else:
            # Use files().get_media() for standard files
            request = drive_service.files().get_media(fileId=file_id)
            print(f"  ⬇️ Downloading file: {file_name}")
        
        # Perform the download
        fh = io.FileIO(file_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
    except Exception as e:
        print(f"  ❌ Error downloading {file_name}: {e}")

def traverse_and_download(drive_service, folder_id, current_path):
    """Recursively lists contents, creates local directories, and downloads files."""
    
    # Ensure the local directory exists, creating the folder structure
    os.makedirs(current_path, exist_ok=True)
    
    page_token = None
    while True:
        # Search query: items inside the current folder ID and not trashed
        query = f"'{folder_id}' in parents and trashed=false"
        
        try:
            results = drive_service.files().list(
                q=query,
                pageSize=100, 
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token
            ).execute()
        except Exception as e:
            # Implement simple exponential backoff for rate limit errors (e.g., 403, 429)
            print(f"  ⚠️ API error encountered: {e}. Retrying in 5 seconds...")
            time.sleep(5)
            continue # Try the current request again

        items = results.get('files', [])
        
        for item in items:
            file_id = item['id']
            file_name = item['name']
            mime_type = item['mimeType']

            if mime_type == 'application/vnd.google-apps.folder':
                # RECURSIVE STEP: Found a subfolder, so we call the function again
                new_path = os.path.join(current_path, file_name)
                print(f"📁 Entering folder: {file_name}")
                traverse_and_download(drive_service, file_id, new_path)
            else:
                # Regular file: proceed with download
                download_file(drive_service, file_id, file_name, current_path)

        page_token = results.get('nextPageToken', None)
        if page_token is None:
            break

if __name__ == '__main__':
    if TARGET_FOLDER_ID == 'YOUR_TARGET_FOLDER_ID':
        print("🛑 ERROR: Please update the TARGET_FOLDER_ID variable in the script with your folder's ID.")
    else:
        print("Starting Google Drive folder download... 🚀")
        
        try:
            drive_service = authenticate()
            
            # Get the name of the root folder to make the local path cleaner
            root_folder_metadata = drive_service.files().get(
                fileId=TARGET_FOLDER_ID, 
                fields='name'
            ).execute()
            root_folder_name = root_folder_metadata.get('name', 'Google_Drive_Folder_Download')
            
            # Build the final base path
            final_base_path = os.path.join(DOWNLOAD_BASE_PATH, root_folder_name)
            
            print(f"Downloading folder '{root_folder_name}'...")
            traverse_and_download(drive_service, TARGET_FOLDER_ID, final_base_path)
            
            print("\n✅ Download complete! Folder structure preserved.")
            print(f"Files saved to: {final_base_path}")

        except Exception as e:
            print(f"\n❌ An unrecoverable error occurred: {e}")