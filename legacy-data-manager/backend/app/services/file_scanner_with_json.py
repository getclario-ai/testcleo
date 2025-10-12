import os
import io
import re
import json
import hashlib
from datetime import datetime
from PIL import Image
import pytesseract
from docx import Document
from pptx import Presentation
from openpyxl import load_workbook
from pdfminer.high_level import extract_text_to_fp
from .google_drive import GoogleDriveService
import asyncio
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# =============================================================================
# RISK SCORING SYSTEM CONFIGURATION
# =============================================================================

# Content-based risk weights for different sensitive information categories
# These weights represent the base risk level for each type of sensitive content
CONTENT_RISK_WEIGHTS = {
    'confidential': 0.4,  # Highest risk - proprietary/classified information
    'pii': 0.3,          # High risk - personally identifiable information (GDPR/HIPAA)
    'financial': 0.2,    # Medium-high risk - financial data and transactions
    'legal': 0.1          # Medium risk - legal documents and compliance
}

# Age-based risk factors (based on file creation date)
# Older files are considered riskier due to potential stale data and forgotten content
AGE_RISK_FACTORS = {
    'high': 0.3,    # Files older than 3 years - high risk (stale data)
    'medium': 0.2,  # Files 1-3 years old - medium risk
    'low': 0.1      # Files less than 1 year old - low risk
}

# Access-based risk factors (based on last accessed date)
# Files that haven't been accessed recently are considered riskier (forgotten files)
ACCESS_RISK_FACTORS = {
    'high': 0.3,    # Not accessed for >3 years - high risk (forgotten files)
    'medium': 0.2,  # Not accessed for 1-3 years - medium risk
    'low': 0.1      # Not accessed for <1 year - low risk
}

# =============================================================================
# RISK CALCULATION FUNCTIONS
# =============================================================================

def get_age_risk_factor(file_created_date):
    """
    Calculate age-based risk factor based on file creation date.
    
    Args:
        file_created_date (datetime): When the file was created
        
    Returns:
        float: Age risk factor (0.1-0.3)
    """
    if not file_created_date:
        # If no creation date available, assume medium risk
        return AGE_RISK_FACTORS['medium']
    
    try:
        # Calculate age in years
        age_years = (datetime.now() - file_created_date).days / 365
        
        if age_years >= 3:
            return AGE_RISK_FACTORS['high']    # >3 years old
        elif age_years >= 1:
            return AGE_RISK_FACTORS['medium']  # 1-3 years old
        else:
            return AGE_RISK_FACTORS['low']     # <1 year old
    except Exception as e:
        logger.warning(f"Error calculating age risk factor: {e}")
        return AGE_RISK_FACTORS['medium']

def get_access_risk_factor(last_accessed_date):
    """
    Calculate access-based risk factor based on last accessed date.
    
    Args:
        last_accessed_date (datetime): When the file was last accessed
        
    Returns:
        float: Access risk factor (0.1-0.3)
    """
    if not last_accessed_date:
        # If no access date available, assume high risk (forgotten files)
        return ACCESS_RISK_FACTORS['high']
    
    try:
        # Calculate time since last access in years
        years_since_access = (datetime.now() - last_accessed_date).days / 365
        
        if years_since_access >= 3:
            return ACCESS_RISK_FACTORS['high']    # >3 years since access
        elif years_since_access >= 1:
            return ACCESS_RISK_FACTORS['medium']  # 1-3 years since access
        else:
            return ACCESS_RISK_FACTORS['low']     # <1 year since access
    except Exception as e:
        logger.warning(f"Error calculating access risk factor: {e}")
        return ACCESS_RISK_FACTORS['medium']

def calculate_weighted_risk_score(file_data, findings):
    """
    Calculate comprehensive risk score using weighted scoring system.
    
    This function implements a multi-factor risk assessment that considers:
    1. Content-based risk (type and amount of sensitive information)
    2. Age-based risk (file creation date)
    3. Access-based risk (last accessed date)
    
    Args:
        file_data (dict): File metadata including creation and access dates
        findings (dict): Sensitive content findings by category
        
    Returns:
        float: Risk score between 0.0 and 1.0
    """
    base_score = 0.0
    
    # Step 1: Calculate content-based risk score
    # Sum up risk weights for all sensitive categories found in the file
    for category in findings.keys():
        base_score += CONTENT_RISK_WEIGHTS.get(category, 0.05)
    
    # Step 2: Add age-based risk factor
    # Older files are riskier due to potential stale data
    age_factor = get_age_risk_factor(file_data.get('createdTime'))
    base_score += age_factor
    
    # Step 3: Add access-based risk factor
    # Files not accessed recently are riskier (potentially forgotten)
    access_factor = get_access_risk_factor(file_data.get('lastAccessedTime'))
    base_score += access_factor
    
    # Step 4: Cap the final score at 1.0 (100% risk)
    final_score = min(base_score, 1.0)
    
    # Log the risk calculation for debugging
    logger.debug(f"Risk calculation for {file_data.get('name', 'unknown')}: "
                f"content={base_score - age_factor - access_factor:.2f}, "
                f"age={age_factor:.2f}, access={access_factor:.2f}, "
                f"total={final_score:.2f}")
    
    return final_score

def get_risk_level_label(risk_score):
    """
    Convert numeric risk score to risk level label.
    
    Args:
        risk_score (float): Risk score between 0.0 and 1.0
        
    Returns:
        str: Risk level label ('high', 'medium', 'low')
    """
    if risk_score >= 0.7:
        return "high"
    elif risk_score >= 0.4:
        return "medium"
    else:
        return "low"

# Optional: Google API modules
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    HAS_GOOGLE_API = True
except ImportError:
    HAS_GOOGLE_API = False

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

file_type_map = {
    'documents': ['docx', 'txt', 'doc', 'rtf', 'odt', 'pages', 'md', 'gdoc'],
    'spreadsheets': ['xlsx', 'xls', 'csv', 'ods', 'numbers', 'gsheet'],
    'presentations': ['pptx', 'ppt', 'odp', 'key', 'gslides'],
    'pdfs': ['pdf'],
    'images': ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tiff', 'heic', 'gdraw'],
    'videos': ['mp4', 'mov', 'avi', 'wmv', 'flv', 'mkv', 'webm'],
    'audio': ['mp3', 'wav', 'ogg', 'm4a', 'wma'],
    'archives': ['zip', 'rar', '7z', 'tar', 'gz'],
    'code': ['py', 'js', 'java', 'cpp', 'h', 'cs', 'php', 'rb', 'swift', 'gs']
}

mime_type_map = {
    # Google Workspace types
    'application/vnd.google-apps.document': 'gdoc',
    'application/vnd.google-apps.spreadsheet': 'gsheet',
    'application/vnd.google-apps.presentation': 'gslides',
    'application/vnd.google-apps.drawing': 'gdraw',
    'application/vnd.google-apps.form': 'gform',
    'application/vnd.google-apps.script': 'gs',
    'application/vnd.google-apps.folder': 'folder',
    
    # Common document types
    'application/pdf': 'pdf',
    'application/msword': 'doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/vnd.ms-excel': 'xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'application/vnd.ms-powerpoint': 'ppt',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
    'application/vnd.oasis.opendocument.text': 'odt',
    'application/vnd.oasis.opendocument.spreadsheet': 'ods',
    'application/vnd.oasis.opendocument.presentation': 'odp',
    'application/x-iwork-pages-sffpages': 'pages',
    'application/x-iwork-numbers-sffnumbers': 'numbers',
    'application/x-iwork-keynote-sffkey': 'key',
    'text/markdown': 'md',
    'text/plain': 'txt',
    'text/rtf': 'rtf',
    
    # Image types
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/webp': 'webp',
    'image/bmp': 'bmp',
    'image/tiff': 'tiff',
    'image/heic': 'heic',
    
    # Video types
    'video/mp4': 'mp4',
    'video/quicktime': 'mov',
    'video/x-msvideo': 'avi',
    'video/x-ms-wmv': 'wmv',
    'video/webm': 'webm',
    'video/x-matroska': 'mkv',
    
    # Audio types
    'audio/mpeg': 'mp3',
    'audio/wav': 'wav',
    'audio/ogg': 'ogg',
    'audio/mp4': 'm4a',
    'audio/x-ms-wma': 'wma',
    
    # Archive types
    'application/zip': 'zip',
    'application/x-rar-compressed': 'rar',
    'application/x-7z-compressed': '7z',
    'application/x-tar': 'tar',
    'application/gzip': 'gz',
    
    # Text and code
    'text/javascript': 'js',
    'text/x-python': 'py',
    'text/x-java': 'java',
    'text/x-c': 'c',
    'text/x-cpp': 'cpp',
    'text/x-csharp': 'cs',
    'text/x-php': 'php',
    'text/x-ruby': 'rb',
    'text/x-swift': 'swift'
}

sensitive_keywords = {
    "pii": [
        "dob", "email", "phone", "address", "ssn", "personal", "pii", 
        "hipaa", "gdpr", "personally identifiable", "customer data",
        "personnel", "employee", "patient", "healthcare"
    ],
    "financial": [
        "credit", "bank", "amount", "revenue", "budget", "roi", "cost",
        "financial", "invoice", "payment", "expense", "profit", "pricing",
        "salary", "investment", "tax"
    ],
    "legal": [
        "license", "contract", "agreement", "legal", "compliance",
        "regulatory", "counsel", "policy", "policies", "terms",
        "regulation", "gdpr", "ccpa", "hipaa", "certification",
        "audit", "liability"
    ],
    "confidential": [
        "confidential", "internal use", "do not distribute", "sensitive",
        "security", "restricted", "proprietary", "classified", "private",
        "secret", "nda", "non-disclosure", "intellectual property",
        "trade secret", "internal only"
    ]
}

patterns = {
    # Matches common credit card formats (Visa, MC, Amex, Discover)
    "credit_card": r"(?:(?:4[0-9]{12}(?:[0-9]{3})?)|(?:5[1-5][0-9]{14})|(?:3[47][0-9]{13})|(?:6(?:011|5[0-9]{2})[0-9]{12}))",
    
    # Matches MM/YY or MM/YYYY with validation
    "expiry_date": r"(?:0[1-9]|1[0-2])\/(?:2[3-9]|[3-9][0-9])",
    
    # Matches SSN with required dashes and surrounding context
    "ssn": r"(?:SSN|Social Security)(?:[^0-9-])*\d{3}-\d{2}-\d{4}",
    
    # Matches email with common domains and validation
    "email": r"(?:[a-zA-Z0-9._%+-]+@(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,})",
    
    # Matches phone with required context and common formats
    "phone": r"(?<![\w/.:-])(?:(?:Phone|Tel|Mobile|Contact|Call|Fax)(?:[^0-9(])+)?(?:\+?1[-. ])?\(?[2-9][0-9]{2}\)?[-. ]?[2-9][0-9]{2}[-. ]?[0-9]{4}(?:\s*(?:ext|x)\.?\s*\d{1,5})?(?![-\d./@])",

    # Matches PA driver's license with validation
    "drivers_license": r"(?:Driver'?s? License|DL|License Number|License #)(?:[^0-9])*(?:[A-Z][0-9]{7}|[A-Z][0-9]{8}|[A-Z][0-9]{12}|\d{7,9}|[A-Z]\d{2}[-\s]?\d{3}[-\s]?\d{3}|[A-Z]\d{3}[-\s]?\d{3}[-\s]?\d{3}|[A-Z]{1,2}\d{4,7})",    
    
    # Matches address with validation and context
    "address_like": r"(?:Address|Location|Street)(?:[^0-9])*\d{1,5}\s[\w\s.]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Circle|Cir|Court|Ct|Way|Place|Pl|Square|Sq)\b",
    
    #Legal Patterns
    "contract_number": r"(?:Contract|Agreement|License)\s*(?:#|Number|No\.?)\s*[A-Z0-9-]+",
    "legal_case": r"(?:Case|Docket)\s*(?:#|Number|No\.?)\s*[A-Z0-9-]+",
    "regulation_ref": r"(?:CFR|U\.S\.C\.|Regulation)\s+\d+[A-Z]?(?:\.\d+)*",
    
    # Confidential Patterns
    "contract_number": r"(?:Contract|Agreement|License)\s*(?:#|Number|No\.?)\s*[A-Z0-9-]+",
    "classification_level": r"(?:TOP SECRET|SECRET|CONFIDENTIAL|RESTRICTED|INTERNAL)",
    "nda_reference": r"(?:NDA|Non-Disclosure|Non Disclosure)\s+(?:Agreement|Contract)"
}

pattern_categories = {
    "credit_card": "financial",
    "expiry_date": "financial", 
    "ssn": "pii",
    "email": "pii",
    "phone": "pii",
    "drivers_license": "pii",
    "address_like": "pii",
    "contract_number": "legal",
    "legal_case": "legal", 
    "regulation_ref": "legal",
    "confidential_header": "confidential",
    "classification_level": "confidential",
    "nda_reference": "confidential"
}

now = datetime.now()

def classify_by_age(modified_time):
    age_days = (now - modified_time).days
    if age_days <= 365:
        return "lessThanOneYear"
    elif age_days <= 1095:
        return "oneToThreeYears"
    else:
        return "moreThanThreeYears"

def initialize_structure():
    """Initialize the structure for file categorization."""
    return {
        "total_documents": 0,
        "total_sensitive": 0,
        "total_duplicates": 0,
        "file_types": {k: [] for k in file_type_map.keys() | {"others"}},
        "sensitive_info": {k: [] for k in sensitive_keywords.keys()},
        "duplicate_files": []
    }

def scan_text(text):
    """
    Scan text for sensitive information using keywords and patterns.
    Returns a dictionary of findings only if sensitive content is detected.
    """
    findings = {cat: [] for cat in sensitive_keywords}
    text_lower = text.lower()
    
    # Check for keywords in each category
    for cat, keywords in sensitive_keywords.items():
        for keyword in keywords:
            # Look for whole word matches only
            if re.search(r'\b' + re.escape(keyword.lower()) + r'\b', text_lower):
                findings[cat].append(keyword)
    
    # Check for pattern matches
    for label, pattern in patterns.items():
        if re.search(pattern, text):
            category = pattern_categories.get(label, "pii")  # Default to pii if not specified
            findings[category].append(label)
    
    # Only return categories that have findings
    return {k: v for k, v in findings.items() if v}

def extract_text_from_file(stream, file_type): 
    try:
        if file_type == 'docx':
            doc = Document(stream)
            return "\n".join([p.text for p in doc.paragraphs])
        elif file_type == 'pptx':
            prs = Presentation(stream)
            return "\n".join([shape.text for slide in prs.slides for shape in slide.shapes if hasattr(shape, "text")])
        elif file_type in ['xlsx', 'xls']:
            wb = load_workbook(stream, read_only=True, data_only=True)
            return "\n".join([str(cell.value) for sheet in wb.worksheets for row in sheet.iter_rows() for cell in row if cell.value])
        elif file_type == 'pdf':
            output = io.StringIO()
            extract_text_to_fp(stream, output)
            return output.getvalue()
        elif file_type in ['jpg', 'jpeg', 'png', 'webp']:
            img = Image.open(stream)
            return pytesseract.image_to_string(img)
        elif file_type == 'txt':
            return stream.read().decode()
    except:
        return ""
    return ""

async def scan_files(source='local', path_or_drive_id='.', output_json='scan_report.json'):
    results = {
        "moreThanThreeYears": initialize_structure(),
        "oneToThreeYears": initialize_structure(),
        "lessThanOneYear": initialize_structure(),
        "scan_complete": False,
        "processed_files": 0,
        "total_files": 0,
        "total_duplicates": 0,
        "total_sensitive_files": 0,
        "failed_files": [],
        "content_hashes": {}
    }

    # Add logging for file type mapping
    logger.info(f"Using file type mapping: {file_type_map}")
    type_counts = {k: 0 for k in file_type_map.keys() | {"others"}}

    if source == 'local':
        all_files = []
        for root, _, files in os.walk(path_or_drive_id):
            for f in files:
                all_files.append(os.path.join(root, f))
        results["total_files"] = len(all_files)

        for filepath in all_files:
            try:
                ext = filepath.split('.')[-1].lower()
                modified_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                age_group = classify_by_age(modified_time)
                file_type = next((k for k, v in file_type_map.items() if ext in v), "others")
                with open(filepath, 'rb') as f:
                    content = extract_text_from_file(f, ext)
                if not content:
                    continue
                results[age_group]["total_documents"] += 1
                results[age_group]["file_types"][file_type].append(filepath)
                findings = scan_text(content)
                if findings:
                    results[age_group]["total_sensitive"] += 1
                    results["total_sensitive_files"] += 1
                    for k, v in findings.items():
                        results[age_group]["sensitive_info"][k].extend(v)
                results["processed_files"] += 1
            except Exception as e:
                logger.error(f"Error processing file {filepath}: {str(e)}")
                results["failed_files"].append(filepath)

    elif source == 'gdrive' and HAS_GOOGLE_API:
        drive_service = GoogleDriveService()
        if not await drive_service.is_authenticated():
            raise ValueError("Not authenticated with Google Drive")

        try:
            files = await drive_service.list_directory(path_or_drive_id, recursive=True)
            results["total_files"] = len(files)
            
            # Track unique sensitive files
            sensitive_file_ids = set()

            for file in files:
                try:
                    file_id = file['id']
                    name = file['name']
                    mime_type = file['mimeType']
                    
                    # Log file type categorization
                    logger.info(f"Processing file: {name} (mime_type: {mime_type})")
                    
                    # Get file extension from mime type or name
                    ext = mime_type_map.get(mime_type, None)
                    if not ext and '.' in name:
                        ext = name.split('.')[-1].lower()
                    
                    if not ext:
                        ext = 'others'

                    modified_time = datetime.fromisoformat(file['modifiedTime'].rstrip("Z"))
                    age_group = classify_by_age(modified_time)

                    # Determine file type category
                    file_type = 'others'
                    for category, extensions in file_type_map.items():
                        if ext in extensions:
                            file_type = category
                            break
                    
                    # Update type counts
                    type_counts[file_type] += 1
                    
                    # Add file to appropriate category
                    file_dict = {
                        "id": file_id,
                        "name": name,
                        "mimeType": mime_type,
                        "modifiedTime": file['modifiedTime'],
                        "size": int(file.get('size', 0))
                    }
                    results[age_group]["file_types"][file_type].append(file_dict)

                    # Only scan content for text-based files
                    if file_type in ['documents', 'spreadsheets', 'presentations', 'pdfs']:
                        try:
                            content = await drive_service.get_file_content(file_id)
                            if content:
                                findings = scan_text(content)
                                if findings:  # If any sensitive content was found
                                    if file_id not in sensitive_file_ids: 
                                        results[age_group]["total_sensitive"] += 1
                                        sensitive_file_ids.add(file_id)
                                        results["total_sensitive_files"] += 1
                                    for k, v in findings.items():
                                        if v:  # Only add if there are findings
                                            results[age_group]["sensitive_info"][k].append({
                                                "file": {
                                                    "id": file_id,
                                                    "name": name,
                                                    "mimeType": mime_type,
                                                    "modifiedTime": file['modifiedTime'],
                                                    "size": int(file.get('size', 0))
                                                },
                                                "confidence": 0.8,
                                                "explanation": f"Found {', '.join(v)}",
                                                "categories": v
                                            })
                        except Exception as e:
                            logger.error(f"Error processing file content {name}: {str(e)}")
                    
                    results["processed_files"] += 1
                except Exception as e:
                    logger.error(f"Error processing file {name}: {str(e)}")
                    results["failed_files"].append(name)

            logger.info(f"Completed processing {results['processed_files']} files")
            logger.info(f"Found {len(sensitive_file_ids)} sensitive files")
            results["scan_complete"] = True
            
            # --- ENRICH FILES WITH SENSITIVITY INFO AND CALCULATE WEIGHTED RISK SCORES ---
            # Build a comprehensive mapping from file_id to all sensitive categories and calculated risk score
            file_sensitivity = {}
            
            # First pass: Collect all sensitive categories for each file
            for age_group in ["moreThanThreeYears", "oneToThreeYears", "lessThanOneYear"]:
                for category, findings in results[age_group]["sensitive_info"].items():
                    for finding in findings:
                        file_info = finding.get("file")
                        if file_info and "id" in file_info:
                            file_id = file_info["id"]
                            
                            # Initialize file sensitivity data if not exists
                            if file_id not in file_sensitivity:
                                file_sensitivity[file_id] = {
                                    "categories": set(),
                                    "file_data": file_info,
                                    "explanations": []
                                }
                            
                            # Add this category to the file's sensitive categories
                            file_sensitivity[file_id]["categories"].add(category)
                            file_sensitivity[file_id]["explanations"].append(finding.get("explanation", ""))
            
            # Second pass: Calculate weighted risk scores for each file
            for file_id, sensitivity_data in file_sensitivity.items():
                # Convert set to list for JSON serialization
                categories_list = list(sensitivity_data["categories"])
                
                # Calculate weighted risk score using the new scoring system
                risk_score = calculate_weighted_risk_score(
                    sensitivity_data["file_data"], 
                    {cat: [cat] for cat in categories_list}  # Convert to findings format
                )
                
                # Determine primary sensitivity reason (highest weighted category)
                primary_category = max(categories_list, key=lambda cat: CONTENT_RISK_WEIGHTS.get(cat, 0))
                
                # Update the sensitivity data with calculated risk score
                file_sensitivity[file_id] = {
                    "sensitivityReason": primary_category,
                    "riskLevel": risk_score,
                    "riskLevelLabel": get_risk_level_label(risk_score),
                    "allCategories": categories_list,
                    "explanation": "; ".join(sensitivity_data["explanations"])
                }
            # --- ENRICH FILES WITH CALCULATED RISK SCORES ---
            # Apply the calculated weighted risk scores to all files in the results
            
            # 1. Apply risk data to files in file_types section
            for age_group in ["moreThanThreeYears", "oneToThreeYears", "lessThanOneYear"]:
                for file_type, files in results[age_group]["file_types"].items():
                    for file in files:
                        if isinstance(file, dict) and "id" in file:
                            sens = file_sensitivity.get(file["id"])
                            if sens:
                                # Apply the new weighted risk scoring data
                                file["sensitivityReason"] = sens["sensitivityReason"]
                                file["riskLevel"] = sens["riskLevel"]
                                file["riskLevelLabel"] = sens["riskLevelLabel"]
                                file["allSensitiveCategories"] = sens["allCategories"]
                                file["sensitivityExplanation"] = sens["explanation"]
                                
                                # Log the risk assessment for debugging
                                logger.debug(f"File {file.get('name', 'unknown')} risk assessment: "
                                           f"score={sens['riskLevel']:.2f}, level={sens['riskLevelLabel']}, "
                                           f"categories={sens['allCategories']}")
                            else:
                                # Non-sensitive files get default values
                                file["sensitivityReason"] = None
                                file["riskLevel"] = None
                                file["riskLevelLabel"] = None
                                file["allSensitiveCategories"] = []
                                file["sensitivityExplanation"] = None
            
            # 2. Apply risk data to files in sensitive_info section (CRITICAL FIX)
            # This ensures that the file objects in findings also have the risk data
            for age_group in ["moreThanThreeYears", "oneToThreeYears", "lessThanOneYear"]:
                for category, findings in results[age_group]["sensitive_info"].items():
                    for finding in findings:
                        file_info = finding.get("file")
                        if file_info and isinstance(file_info, dict) and "id" in file_info:
                            sens = file_sensitivity.get(file_info["id"])
                            if sens:
                                # Apply the new weighted risk scoring data to the file object in the finding
                                file_info["sensitivityReason"] = sens["sensitivityReason"]
                                file_info["riskLevel"] = sens["riskLevel"]
                                file_info["riskLevelLabel"] = sens["riskLevelLabel"]
                                file_info["allSensitiveCategories"] = sens["allCategories"]
                                file_info["sensitivityExplanation"] = sens["explanation"]
                                
                                logger.debug(f"Sensitive info file {file_info.get('name', 'unknown')} risk assessment: "
                                           f"score={sens['riskLevel']:.2f}, level={sens['riskLevelLabel']}, "
                                           f"categories={sens['allCategories']}")
            # --- CALCULATE SUMMARY STATISTICS ---
            # Count unique sensitive files per age group for summary statistics
            for age_group in ["moreThanThreeYears", "oneToThreeYears", "lessThanOneYear"]:
                unique_sensitive_ids = set()
                for category, findings in results[age_group]["sensitive_info"].items():
                    for finding in findings:
                        file_info = finding.get("file")
                        if file_info and "id" in file_info:
                            unique_sensitive_ids.add(file_info["id"])
                            # Debug log file with new risk scoring information
                            sens_data = file_sensitivity.get(file_info["id"], {})
                            logger.info(f"[DEBUG] Sensitive file - Age group: {age_group}, Category: {category}, "
                                       f"Name: {file_info.get('name')}, Size: {file_info.get('size')}, "
                                       f"Risk Score: {sens_data.get('riskLevel', 'N/A'):.2f}, "
                                       f"Risk Level: {sens_data.get('riskLevelLabel', 'N/A')}")
                results[age_group]["total_sensitive"] = len(unique_sensitive_ids)
            
            # Log summary of risk distribution for the entire scan
            total_files = len(file_sensitivity)
            high_risk_files = sum(1 for data in file_sensitivity.values() if data.get('riskLevelLabel') == 'high')
            medium_risk_files = sum(1 for data in file_sensitivity.values() if data.get('riskLevelLabel') == 'medium')
            low_risk_files = sum(1 for data in file_sensitivity.values() if data.get('riskLevelLabel') == 'low')
            
            logger.info(f"Risk distribution summary: High={high_risk_files}, Medium={medium_risk_files}, Low={low_risk_files}")
            logger.info(f"Total sensitive files processed: {total_files}")
       
        except Exception as e:
            logger.error(f"Error scanning files: {str(e)}")
            raise

    return results
