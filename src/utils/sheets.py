"""
Google Sheets Integration for FunTrivia Scraper

USAGE EXAMPLES:

1. Test Google Sheets connection:
   python src/main.py --sheets-test-only --sheets-credentials credentials/service-account.json --sheets-id 1abc123def456

2. Enable Google Sheets upload via command line (recommended):
   python src/main.py --upload-to-sheets --sheets-credentials credentials/service-account.json --sheets-id 1abc123def456

3. Enable Google Sheets upload via config file:
   Edit config/settings.json:
   {
     "google_sheets": {
       "enabled": true,
       "credentials_file": "credentials/service-account.json", 
       "spreadsheet_id": "1abc123def456"
     }
   }

4. Explicitly disable Google Sheets (overrides config):
   python src/main.py --no-sheets-upload

SETUP REQUIREMENTS:
- Google Cloud Project with Google Sheets API enabled
- Service Account with credentials JSON file
- Google Spreadsheet shared with service account email
- Valid spreadsheet ID from the spreadsheet URL

By default, Google Sheets upload is DISABLED for privacy and security.
"""

import gspread # type: ignore
from oauth2client.service_account import ServiceAccountCredentials # type: ignore
import pandas as pd # type: ignore
from typing import Dict, Any, Tuple, Optional
import logging
import os
import json

class GoogleSheetsUploader:
    """
    Google Sheets uploader with comprehensive validation and error handling.
    
    This class handles uploading CSV data to Google Sheets with proper authentication,
    validation, and graceful error handling. By design, it requires explicit setup
    and will not attempt uploads without valid credentials and configuration.
    """
    
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        self.logger = logging.getLogger(__name__)
        self.credentials_file = credentials_file
        self.spreadsheet_id = spreadsheet_id
        self.client = None
        self.spreadsheet = None

    def validate_setup(self) -> Tuple[bool, str]:
        """
        Comprehensive validation of Google Sheets setup.
        
        Checks:
        - Credentials file exists and is valid JSON
        - Required fields are present in credentials
        - Service account authentication works
        - Spreadsheet exists and is accessible
        
        Returns:
            Tuple of (is_valid: bool, message: str)
        """
        try:
            # Check if credentials file exists
            if not os.path.exists(self.credentials_file):
                return False, f"Credentials file not found: {self.credentials_file}"
            
            # Validate credentials file format
            try:
                with open(self.credentials_file, 'r') as f:
                    creds_data = json.load(f)
                
                required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
                missing_fields = [field for field in required_fields if field not in creds_data]
                
                if missing_fields:
                    return False, f"Missing required fields in credentials: {', '.join(missing_fields)}"
                
                if creds_data.get('type') != 'service_account':
                    return False, "Credentials file must be for a service account"
                    
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON in credentials file: {e}"
            
            # Check spreadsheet ID format
            if not self.spreadsheet_id or len(self.spreadsheet_id) < 20:
                return False, "Invalid or missing spreadsheet ID"
            
            # Test authentication
            auth_success, auth_message = self._test_authentication()
            if not auth_success:
                return False, f"Authentication failed: {auth_message}"
            
            # Test spreadsheet access
            access_success, access_message = self._test_spreadsheet_access()
            if not access_success:
                return False, f"Spreadsheet access failed: {access_message}"
            
            return True, "Google Sheets setup is valid"
            
        except Exception as e:
            return False, f"Validation error: {e}"

    def _test_authentication(self) -> Tuple[bool, str]:
        """Test Google Sheets API authentication."""
        try:
            scope = ['https://spreadsheets.google.com/feeds',
                    'https://www.googleapis.com/auth/drive']
            credentials = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_file, scope)
            self.client = gspread.authorize(credentials)
            
            # Test basic API access
            self.client.list_permissions(self.spreadsheet_id)
            
            service_email = credentials.service_account_email
            self.logger.info(f"Successfully authenticated with service account: {service_email}")
            return True, f"Authenticated as {service_email}"
            
        except FileNotFoundError:
            return False, "Credentials file not found"
        except json.JSONDecodeError:
            return False, "Invalid credentials file format"
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 403:
                return False, "API access forbidden - check if Google Sheets API is enabled"
            elif e.response.status_code == 404:
                return False, "Spreadsheet not found or not shared with service account"
            else:
                return False, f"API error: {e}"
        except Exception as e:
            return False, f"Authentication error: {e}"

    def _test_spreadsheet_access(self) -> Tuple[bool, str]:
        """Test access to the specific spreadsheet."""
        try:
            if not self.client:
                return False, "Not authenticated"
            
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            # Try to access basic spreadsheet info
            title = self.spreadsheet.title
            worksheets = self.spreadsheet.worksheets()
            
            self.logger.info(f"Successfully accessed spreadsheet: '{title}' with {len(worksheets)} worksheets")
            return True, f"Access to '{title}' confirmed ({len(worksheets)} worksheets)"
            
        except gspread.exceptions.SpreadsheetNotFound:
            return False, "Spreadsheet not found - check the spreadsheet ID"
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 403:
                return False, "Access denied - ensure spreadsheet is shared with service account"
            else:
                return False, f"API error accessing spreadsheet: {e}"
        except Exception as e:
            return False, f"Error accessing spreadsheet: {e}"

    def authenticate(self) -> None:
        """Authenticate with Google Sheets API with enhanced error handling."""
        try:
            # First validate setup
            is_valid, message = self.validate_setup()
            if not is_valid:
                raise Exception(f"Setup validation failed: {message}")
            
            # If validation passed, client should already be set
            if not self.client:
                scope = ['https://spreadsheets.google.com/feeds',
                        'https://www.googleapis.com/auth/drive']
                credentials = ServiceAccountCredentials.from_json_keyfile_name(
                    self.credentials_file, scope)
                self.client = gspread.authorize(credentials)
            
            self.logger.info("Google Sheets authentication successful")
            
        except Exception as e:
            self.logger.error(f"Failed to authenticate with Google Sheets: {e}")
            raise

    def get_or_create_worksheet(self, worksheet_name: str, rows: int = 1000, cols: int = 20):
        """Get existing worksheet or create new one with error handling."""
        try:
            if not self.spreadsheet:
                self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            # Try to get existing worksheet
            try:
                worksheet = self.spreadsheet.worksheet(worksheet_name)
                self.logger.info(f"Found existing worksheet: {worksheet_name}")
                return worksheet
            except gspread.exceptions.WorksheetNotFound:
                # Create new worksheet
                worksheet = self.spreadsheet.add_worksheet(
                    title=worksheet_name,
                    rows=rows,
                    cols=cols
                )
                self.logger.info(f"Created new worksheet: {worksheet_name}")
                return worksheet
                
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 403:
                raise Exception(f"Permission denied creating worksheet '{worksheet_name}' - check sharing permissions")
            else:
                raise Exception(f"API error with worksheet '{worksheet_name}': {e}")
        except Exception as e:
            raise Exception(f"Error handling worksheet '{worksheet_name}': {e}")

    def upload_dataframe(self, df: pd.DataFrame, worksheet_name: str) -> None:
        """Upload a DataFrame to a specific worksheet with validation."""
        if not self.client:
            self.authenticate()

        try:
            # Validate DataFrame
            if df.empty:
                self.logger.warning(f"DataFrame for {worksheet_name} is empty, skipping upload")
                return
            
            # Get or create worksheet
            worksheet = self.get_or_create_worksheet(worksheet_name)

            # Validate data size
            max_rows = 1000000  # Google Sheets limit
            max_cols = 18278   # Google Sheets limit
            
            if len(df) > max_rows:
                raise Exception(f"DataFrame too large: {len(df)} rows (max: {max_rows})")
            if len(df.columns) > max_cols:
                raise Exception(f"DataFrame too wide: {len(df.columns)} columns (max: {max_cols})")

            # Clear existing content
            worksheet.clear()

            # Convert DataFrame to list of lists with validation
            data = []
            
            # Add headers
            headers = df.columns.tolist()
            data.append(headers)
            
            # Add data rows
            for _, row in df.iterrows():
                row_data = []
                for value in row:
                    # Handle different data types and ensure they're serializable
                    if pd.isna(value):
                        row_data.append('')
                    elif isinstance(value, (int, float, str, bool)):
                        row_data.append(str(value))
                    else:
                        row_data.append(str(value))
                data.append(row_data)

            # Upload data in batches to avoid API limits
            batch_size = 1000
            if len(data) <= batch_size:
                worksheet.update('A1', data)
            else:
                # Upload in batches
                for i in range(0, len(data), batch_size):
                    batch = data[i:i + batch_size]
                    start_row = i + 1
                    end_row = start_row + len(batch) - 1
                    range_name = f'A{start_row}:Z{end_row}'
                    worksheet.update(range_name, batch)
                    self.logger.info(f"Uploaded batch {i//batch_size + 1} for {worksheet_name}")

            self.logger.info(f"Successfully uploaded {len(df)} rows to {worksheet_name}")
            
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 429:
                raise Exception("Rate limit exceeded - try reducing upload frequency")
            elif e.response.status_code == 403:
                raise Exception("Permission denied - check spreadsheet sharing permissions")
            else:
                raise Exception(f"Google Sheets API error: {e}")
        except Exception as e:
            self.logger.error(f"Failed to upload data to {worksheet_name}: {e}")
            raise

    def upload_csv_files(self, csv_files: Dict[str, str]) -> None:
        """
        Upload multiple CSV files to their respective worksheets with progress tracking.
        
        Args:
            csv_files: Dictionary mapping question types to CSV file paths
        """
        if not csv_files:
            self.logger.info("No CSV files to upload")
            return

        total_files = len(csv_files)
        successful_uploads = 0
        failed_uploads = []

        self.logger.info(f"Starting upload of {total_files} CSV files to Google Sheets")

        for question_type, file_path in csv_files.items():
            try:
                self.logger.info(f"Processing {question_type} ({successful_uploads + 1}/{total_files})")
                
                # Validate file exists and is readable
                if not os.path.exists(file_path):
                    raise Exception(f"CSV file not found: {file_path}")
                
                # Read CSV with validation
                try:
                    df = pd.read_csv(file_path)
                except pd.errors.EmptyDataError:
                    self.logger.warning(f"CSV file {file_path} is empty, skipping")
                    continue
                except Exception as e:
                    raise Exception(f"Error reading CSV file {file_path}: {e}")
                
                # Upload to worksheet
                worksheet_name = self.get_worksheet_name(question_type)
                self.upload_dataframe(df, worksheet_name)
                successful_uploads += 1
                
            except Exception as e:
                error_msg = f"Failed to upload {question_type}: {e}"
                self.logger.error(error_msg)
                failed_uploads.append((question_type, str(e)))
                continue

        # Report results
        self.logger.info(f"Upload completed: {successful_uploads}/{total_files} successful")
        if failed_uploads:
            self.logger.error(f"Failed uploads: {[f[0] for f in failed_uploads]}")
            for question_type, error in failed_uploads:
                self.logger.error(f"  {question_type}: {error}")

    @staticmethod
    def get_worksheet_name(question_type: str) -> str:
        """Map question type to worksheet name."""
        mapping = {
            'multiple_choice': 'Multiple Choice',
            'true_false': 'True/False',
            'sound': 'Sound'
        }
        return mapping.get(question_type, question_type)

    def get_spreadsheet_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the spreadsheet."""
        try:
            if not self.client:
                self.authenticate()
            
            if not self.spreadsheet:
                self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            worksheets = self.spreadsheet.worksheets()
            
            info = {
                'title': self.spreadsheet.title,
                'id': self.spreadsheet.id,
                'url': self.spreadsheet.url,
                'worksheets': [
                    {
                        'title': ws.title,
                        'id': ws.id,
                        'row_count': ws.row_count,
                        'col_count': ws.col_count
                    } for ws in worksheets
                ]
            }
            
            return info
            
        except Exception as e:
            self.logger.error(f"Error getting spreadsheet info: {e}")
            return None


def print_setup_instructions():
    """Print detailed Google Sheets setup instructions."""
    instructions = """
📊 GOOGLE SHEETS SETUP INSTRUCTIONS

1. CREATE GOOGLE CLOUD PROJECT:
   • Go to https://console.cloud.google.com/
   • Create a new project or select an existing one
   • Note your project ID

2. ENABLE GOOGLE SHEETS API:
   • Navigate to APIs & Services > Library
   • Search for "Google Sheets API"
   • Click on it and press "Enable"

3. CREATE SERVICE ACCOUNT:
   • Go to APIs & Services > Credentials
   • Click "Create Credentials" > "Service Account"
   • Fill in service account name (e.g., "funtrivia-scraper")
   • Click "Create and Continue"
   • Skip role assignment (click "Continue")
   • Click "Done"

4. GENERATE CREDENTIALS:
   • Click on the service account you just created
   • Go to "Keys" tab
   • Click "Add Key" > "Create New Key"
   • Select "JSON" format
   • Download the JSON file

5. SAVE CREDENTIALS:
   • Create a credentials/ directory in your project
   • Save the downloaded JSON as credentials/service-account.json
   • Make sure the file is not publicly accessible

6. CREATE GOOGLE SPREADSHEET:
   • Go to https://sheets.google.com/
   • Create a new spreadsheet
   • Copy the spreadsheet ID from the URL:
     https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit

7. SHARE SPREADSHEET:
   • Open the JSON credentials file
   • Copy the "client_email" value (service account email)
   • In your spreadsheet, click "Share"
   • Add the service account email with "Editor" permissions

8. TEST CONNECTION:
   python src/main.py --sheets-test-only --sheets-credentials credentials/service-account.json --sheets-id YOUR_SPREADSHEET_ID

9. USE WITH SCRAPER:
   python src/main.py --upload-to-sheets --sheets-credentials credentials/service-account.json --sheets-id YOUR_SPREADSHEET_ID

SECURITY NOTES:
• Never commit credentials files to version control
• Add credentials/ to your .gitignore file
• Use environment variables in production
• Regularly rotate service account keys
"""
    print(instructions)


def test_google_sheets_setup(credentials_file: str, spreadsheet_id: str) -> bool:
    """
    Test Google Sheets setup and print detailed results.
    
    Args:
        credentials_file: Path to service account JSON file
        spreadsheet_id: Google Spreadsheet ID
        
    Returns:
        True if setup is valid, False otherwise
    """
    print("🔍 Testing Google Sheets Setup")
    print("-" * 40)
    
    uploader = GoogleSheetsUploader(credentials_file, spreadsheet_id)
    
    # Run validation
    is_valid, message = uploader.validate_setup()
    
    if is_valid:
        print("✅ Google Sheets setup is valid!")
        print(f"   {message}")
        
        # Get additional info
        info = uploader.get_spreadsheet_info()
        if info:
            print(f"\nSpreadsheet Details:")
            print(f"  Title: {info['title']}")
            print(f"  URL: {info['url']}")
            print(f"  Worksheets: {len(info['worksheets'])}")
            for ws in info['worksheets']:
                print(f"    • {ws['title']} ({ws['row_count']} rows × {ws['col_count']} cols)")
        
        print("\n✅ Google Sheets integration is ready to use!")
        print("   Use --upload-to-sheets flag to enable uploads.")
        
        return True
    else:
        print("❌ Google Sheets setup failed!")
        print(f"   Error: {message}")
        print("\n🔧 Troubleshooting steps:")
        print("1. Ensure Google Sheets API is enabled in Google Cloud Console")
        print("2. Check that credentials file is valid service account JSON")
        print("3. Verify spreadsheet is shared with service account email")
        print("4. Confirm spreadsheet ID is correct")
        print("\nFor detailed setup instructions, run:")
        print("python -c \"from src.utils.sheets import print_setup_instructions; print_setup_instructions()\"")
        
        return False 