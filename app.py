import streamlit as st
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import base64
from io import BytesIO
from PIL import Image
import os
import hashlib
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BUCKET_NAME = "sdh-saree-dhothi-ceremony"  # Replace with your bucket name
IMAGES_PER_PAGE = 24
MAX_IMAGE_SIZE = (400, 400)  # Thumbnail size for display
FULLSCREEN_IMAGE_SIZE = (1440, 1440)  # Fullscreen image size

# Security Configuration
MAX_ATTEMPTS = 5  # Maximum login attempts
LOCKOUT_DURATION = 60*60  # Lockout duration in seconds (60 minutes)
SESSION_TIMEOUT = 3600*12  # Session timeout in seconds (12 hours)

# Custom CSS for mobile-first responsive design
def load_custom_css():
    st.markdown("""
    <style>
    /* Mobile-first responsive design */
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 0.5rem;
        padding-right: 0.5rem;
        max-width: 100%;
    }
    
    /* Responsive grid for images */
    .image-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 10px;
        margin: 10px 0;
    }
    
    @media (min-width: 768px) {
        .image-grid {
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
    
    @media (min-width: 1024px) {
        .image-grid {
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }
        .main .block-container {
            padding-left: 2rem;
            padding-right: 2rem;
        }
    }
    
    /* Image container styling */
    .image-container {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: transform 0.2s, box-shadow 0.2s;
        background: white;
    }
    
    .image-container:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    
    /* Image styling */
    .image-container img {
        width: 100%;
        height: 200px;
        object-fit: cover;
        border-bottom: 1px solid #e0e0e0;
    }
    
    /* Image info section */
    .image-info {
        padding: 8px;
        background: #f8f9fa;
    }
    
    .image-filename {
        font-size: 0.8rem;
        font-weight: 600;
        color: #333;
        margin-bottom: 4px;
        word-break: break-word;
    }
    
    .image-details {
        font-size: 0.7rem;
        color: #666;
        margin-bottom: 8px;
    }
    
    /* Button styling */
    .action-buttons {
        display: flex;
        gap: 5px;
        justify-content: space-between;
    }
    
    .btn-small {
        font-size: 0.7rem !important;
        padding: 4px 8px !important;
        min-height: 28px !important;
        border-radius: 4px !important;
    }
    
    /* Fullscreen view */
    .fullscreen-header {
        background: #f8f9fa;
        padding: 10px;
        border-radius: 8px;
        margin-bottom: 20px;
        text-align: center;
    }
    
    .fullscreen-close-btn {
        background: #dc3545;
        color: white;
        border: none;
        padding: 12px 24px;
        border-radius: 8px;
        font-size: 16px;
        cursor: pointer;
        width: 100%;
        margin-bottom: 20px;
    }
    
    /* Folder button styling */
    .folder-button {
        display: block;
        width: 100%;
        padding: 12px;
        margin: 5px 0;
        border: 1px solid #ddd;
        border-radius: 8px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        text-decoration: none;
        font-weight: 500;
        transition: all 0.2s;
        text-align: center;
    }
    
    .folder-button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* Pagination styling */
    .pagination-container {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 10px;
        margin: 20px 0;
        flex-wrap: wrap;
    }
    
    .pagination-info {
        font-size: 0.9rem;
        color: #666;
        text-align: center;
        margin: 0 10px;
    }
    
    /* Status indicators */
    .status-container {
        display: flex;
        flex-direction: column;
        gap: 5px;
        margin-bottom: 20px;
    }
    
    @media (min-width: 768px) {
        .status-container {
            flex-direction: row;
            justify-content: space-between;
            align-items: center;
        }
    }
    
    /* Loading animation */
    .loading-placeholder {
        background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
        background-size: 200% 100%;
        animation: loading 1.5s infinite;
        height: 200px;
        border-radius: 4px;
    }
    
    @keyframes loading {
        0% {
            background-position: 200% 0;
        }
        100% {
            background-position: -200% 0;
        }
    }
    
    /* Hide Streamlit's default sidebar toggle on mobile */
    @media (max-width: 768px) {
        .css-1d391kg {
            padding-left: 1rem;
        }
    }
    </style>
    """, unsafe_allow_html=True)

# Security functions
def hash_pin(pin):
    """Hash PIN using SHA-256"""
    return hashlib.sha256(pin.encode()).hexdigest()

def get_correct_pin_hash():
    """Get the correct PIN hash from environment variable"""
    pin = os.environ.get('APP_PIN')
    if not pin:
        st.error("⚠️ APP_PIN not set in environment variables!")
        st.stop()
    return hash_pin(pin)

def initialize_security_state():
    """Initialize security-related session state"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'auth_time' not in st.session_state:
        st.session_state.auth_time = None
    if 'failed_attempts' not in st.session_state:
        st.session_state.failed_attempts = 0
    if 'lockout_until' not in st.session_state:
        st.session_state.lockout_until = None

def is_locked_out():
    """Check if user is currently locked out"""
    if st.session_state.lockout_until:
        if datetime.now() < st.session_state.lockout_until:
            return True
        else:
            # Lockout period expired, reset
            st.session_state.lockout_until = None
            st.session_state.failed_attempts = 0
    return False

def is_session_expired():
    """Check if the current session has expired"""
    if st.session_state.auth_time:
        return datetime.now() - st.session_state.auth_time > timedelta(seconds=SESSION_TIMEOUT)
    return True

def authenticate_user():
    """Handle user authentication"""
    initialize_security_state()
    
    # Check if session expired
    if st.session_state.authenticated and is_session_expired():
        st.session_state.authenticated = False
        st.session_state.auth_time = None
        st.warning("Session expired. Please log in again.")
        st.rerun()
    
    # If already authenticated and session valid, return True
    if st.session_state.authenticated and not is_session_expired():
        return True
    
    # Show login form
    st.title("🔐 Authentication Required")
    st.info("Please enter your PIN to access the photo browser.")
    
    # Check if locked out
    if is_locked_out():
        remaining_time = int((st.session_state.lockout_until - datetime.now()).total_seconds())
        st.error(f"🚫 Too many failed attempts. Please try again in {remaining_time} seconds.")
        
        # Auto-refresh every 10 seconds during lockout
        time.sleep(10)
        st.rerun()
        return False
    
    # Show remaining attempts
    remaining_attempts = MAX_ATTEMPTS - st.session_state.failed_attempts
    if st.session_state.failed_attempts > 0:
        st.warning(f"⚠️ {remaining_attempts} attempts remaining before lockout.")
    
    # PIN input form
    with st.form("login_form"):
        pin_input = st.text_input(
            "Enter PIN:", 
            type="password", 
            placeholder="Enter your 4-digit PIN",
            max_chars=10,
            help="Enter the PIN to access your photos"
        )
        
        submit_button = st.form_submit_button("🔓 Login", use_container_width=True)
        
        if submit_button:
            if not pin_input:
                st.error("Please enter a PIN.")
                return False
            
            # Verify PIN
            correct_pin_hash = get_correct_pin_hash()
            entered_pin_hash = hash_pin(pin_input)
            
            if entered_pin_hash == correct_pin_hash:
                # Successful login
                st.session_state.authenticated = True
                st.session_state.auth_time = datetime.now()
                st.session_state.failed_attempts = 0
                st.session_state.lockout_until = None
                st.success("✅ Authentication successful!")
                time.sleep(1)
                st.rerun()
            else:
                # Failed login
                st.session_state.failed_attempts += 1
                
                if st.session_state.failed_attempts >= MAX_ATTEMPTS:
                    # Lockout user
                    st.session_state.lockout_until = datetime.now() + timedelta(seconds=LOCKOUT_DURATION)
                    st.error(f"🚫 Too many failed attempts! Locked out for {LOCKOUT_DURATION // 60} minutes.")
                else:
                    remaining = MAX_ATTEMPTS - st.session_state.failed_attempts
                    st.error(f"❌ Incorrect PIN. {remaining} attempts remaining.")
                
                time.sleep(2)
                st.rerun()
    
    return False

def logout_user():
    """Handle user logout"""
    st.session_state.authenticated = False
    st.session_state.auth_time = None
    st.session_state.failed_attempts = 0
    st.session_state.lockout_until = None
    st.rerun()

# Initialize S3 client
@st.cache_resource
def get_s3_client():
    """Initialize S3 client with credentials"""
    try:
        return boto3.client(
            's3',
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
            region_name='ap-south-1'
        )
    except NoCredentialsError:
        st.error("AWS credentials not found. Please configure your credentials.")
        return None

def list_folders(s3_client, bucket, prefix=""):
    """List folders in S3 bucket"""
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            Delimiter='/'
        )
        
        folders = []
        if 'CommonPrefixes' in response:
            for obj in response['CommonPrefixes']:
                folder_name = obj['Prefix'].rstrip('/').split('/')[-1]
                folders.append((folder_name, obj['Prefix']))
        
        return folders
    except ClientError as e:
        st.error(f"Error listing folders: {e}")
        return []

@st.cache_data(ttl=300)  # Cache for 5 minutes
def list_images(bucket, prefix, max_keys=1000):
    """List image files in S3 with caching"""
    s3_client = get_s3_client()
    if not s3_client:
        return []
    
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            MaxKeys=max_keys
        )
        
        images = []
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                # Filter for common image extensions and exclude zero-byte files
                if (key.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')) 
                    and obj['Size'] > 0):
                    images.append({
                        'key': key,
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'],
                        'filename': key.split('/')[-1]
                    })
        
        return sorted(images, key=lambda x: x['last_modified'], reverse=True)
    except ClientError as e:
        st.error(f"Error listing images: {e}")
        return []

@st.cache_data(ttl=3600)  # Cache images for 1 hour
def get_image_thumbnail(bucket, key):
    """Get image thumbnail with caching"""
    s3_client = get_s3_client()
    if not s3_client:
        return None
    
    try:
        # Get object from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        image_data = response['Body'].read()
        
        # Validate that we have data
        if not image_data or len(image_data) == 0:
            st.error(f"Empty image file: {key}")
            return None
        
        # Try to open and process the image
        try:
            image_buffer = BytesIO(image_data)
            image = Image.open(image_buffer)
            
            # Convert to RGB if necessary (handles RGBA, P mode, etc.)
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            
            # Create thumbnail
            image.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
            
            # Convert to base64 for display
            output_buffer = BytesIO()
            image.save(output_buffer, format='JPEG', quality=85, optimize=True)
            img_base64 = base64.b64encode(output_buffer.getvalue()).decode()
            
            return img_base64
            
        except Exception as img_error:
            # Log the specific image processing error
            error_msg = f"Cannot process image {key.split('/')[-1]}: {str(img_error)}"
            print(error_msg)  # For debugging
            return None
            
    except ClientError as e:
        error_msg = f"S3 error loading {key}: {e}"
        print(error_msg)  # For debugging
        return None
    except Exception as e:
        error_msg = f"Unexpected error loading {key}: {e}"
        print(error_msg)  # For debugging
        return None

@st.cache_data(ttl=3600)  # Cache fullscreen images for 1 hour
def get_fullscreen_image(bucket, key):
    """Get full-resolution image for fullscreen display"""
    s3_client = get_s3_client()
    if not s3_client:
        return None
    
    try:
        # Get object from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        image_data = response['Body'].read()
        
        # Validate that we have data
        if not image_data or len(image_data) == 0:
            return None
        
        # Try to open and process the image
        try:
            image_buffer = BytesIO(image_data)
            image = Image.open(image_buffer)
            
            # Convert to RGB if necessary
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            
            # Resize for fullscreen if too large
            if image.size[0] > FULLSCREEN_IMAGE_SIZE[0] or image.size[1] > FULLSCREEN_IMAGE_SIZE[1]:
                image.thumbnail(FULLSCREEN_IMAGE_SIZE, Image.Resampling.LANCZOS)
            
            # Convert to base64 for display
            output_buffer = BytesIO()
            image.save(output_buffer, format='JPEG', quality=95, optimize=True)
            img_base64 = base64.b64encode(output_buffer.getvalue()).decode()
            
            return img_base64
            
        except Exception as img_error:
            return None
            
    except Exception as e:
        return None

def show_fullscreen_image(image_base64, filename):
    """Display fullscreen image view"""
    st.markdown(f"""
    <div class="fullscreen-header">
        <h3>🔍 {filename}</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # Close button at the top
    if st.button("✕ Close", key="close_fullscreen", use_container_width=True, type="primary"):
        st.session_state.fullscreen_image = None
        st.rerun()
    
    # Display the image
    st.image(f"data:image/jpeg;base64,{image_base64}", use_container_width=True)
    
    # Close button at the bottom
    if st.button("← Back to Gallery", key="back_to_gallery", use_container_width=True):
        st.session_state.fullscreen_image = None
        st.rerun()

def paginate_images(images, page, per_page):
    """Paginate image list"""
    start = page * per_page
    end = start + per_page
    return images[start:end], len(images)

def main():
    st.set_page_config(
        page_title="SDH Ceremony Photos",
        page_icon="📸",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Load custom CSS
    load_custom_css()
    
    # Authentication check - this runs first
    if not authenticate_user():
        return
    
    # Initialize fullscreen state
    if 'fullscreen_image' not in st.session_state:
        st.session_state.fullscreen_image = None
    
    # Show fullscreen image if requested
    if st.session_state.fullscreen_image:
        show_fullscreen_image(
            st.session_state.fullscreen_image['data'],
            st.session_state.fullscreen_image['filename']
        )
        return
    
    # Main app content (only shown if authenticated and not in fullscreen mode)
    st.title("📸 SDH Ceremony Photos")
    
    # Show authentication status and logout button
    with st.container():
        st.markdown('<div class="status-container">', unsafe_allow_html=True)
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if st.session_state.auth_time:
                session_remaining = SESSION_TIMEOUT - int((datetime.now() - st.session_state.auth_time).total_seconds())
                st.success(f"✅ Authenticated | Session: {session_remaining // 60}min remaining", icon="✅")
        
        with col2:
            if st.button("🚪 Logout", use_container_width=True):
                logout_user()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Check if environment variables are loaded
    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        st.error("⚠️ AWS credentials not found in environment variables!")
        st.info("Please ensure your .env file contains:\n- AWS_ACCESS_KEY_ID=your_access_key\n- AWS_SECRET_ACCESS_KEY=your_secret_key")
        return
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Settings")
        images_per_page = st.slider("Images per page", 8, 60, 20, help="Adjust for better performance")
        st.header("📱 Mobile Optimized")
        st.info("This app is designed for mobile-first experience")
    
    # Initialize session state
    if 'current_path' not in st.session_state:
        st.session_state.current_path = ""
    if 'page' not in st.session_state:
        st.session_state.page = 0
    if 'path_history' not in st.session_state:
        st.session_state.path_history = []
    
    s3_client = get_s3_client()
    if not s3_client:
        return
    
    # Test S3 connection
    try:
        s3_client.head_bucket(Bucket=BUCKET_NAME)
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            st.error(f"Bucket '{BUCKET_NAME}' not found.")
        elif e.response['Error']['Code'] == '403':
            st.error(f"Access denied to bucket '{BUCKET_NAME}'. Check your permissions.")
        else:
            st.error(f"Error accessing bucket: {e}")
        return
    except Exception as e:
        st.error(f"Error connecting to S3: {e}")
        return
    
    # Breadcrumb navigation
    if st.session_state.current_path:
        path_parts = st.session_state.current_path.strip('/').split('/')
        breadcrumb = "🏠 Home"
        for i, part in enumerate(path_parts):
            if part:
                breadcrumb += f" › {part}"
        st.markdown(f"### {breadcrumb}")
        
        if st.button("⬅️ Back", use_container_width=True):
            if st.session_state.path_history:
                st.session_state.current_path = st.session_state.path_history.pop()
            else:
                st.session_state.current_path = ""
            st.session_state.page = 0
            st.rerun()
    else:
        st.markdown("### 🏠 Home")
    
    # List folders at current level
    folders = list_folders(s3_client, BUCKET_NAME, st.session_state.current_path)
    
    if folders:
        st.markdown("#### 📂 Folders")
        for folder_name, folder_path in folders:
            if st.button(f"📁 {folder_name}", key=f"folder_{folder_name}", use_container_width=True):
                st.session_state.path_history.append(st.session_state.current_path)
                st.session_state.current_path = folder_path
                st.session_state.page = 0
                st.rerun()
    
    # List and display images
    images = list_images(BUCKET_NAME, st.session_state.current_path)
    
    if not images:
        st.info("📷 No images found in this folder.")
        return
    
    # Pagination
    current_images, total_images = paginate_images(
        images, st.session_state.page, images_per_page
    )
    
    # Pagination controls
    total_pages = (total_images - 1) // images_per_page + 1
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("⬅️ Previous", disabled=st.session_state.page == 0, use_container_width=True):
            st.session_state.page = max(0, st.session_state.page - 1)
            st.rerun()
    
    with col2:
        st.markdown(f"""
        <div class="pagination-info">
            Page {st.session_state.page + 1} of {total_pages}<br>
            <small>{total_images} images total</small>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        if st.button("Next ➡️", disabled=st.session_state.page >= total_pages - 1, use_container_width=True):
            st.session_state.page = min(total_pages - 1, st.session_state.page + 1)
            st.rerun()
    
    # Display images in responsive grid
    if current_images:
        st.markdown("#### 🖼️ Images")
        
        # Create responsive columns
        cols = st.columns(2)  # 2 columns for mobile
        if st.session_state.get('screen_width', 768) > 768:
            cols = st.columns(3)  # 3 columns for tablet
        if st.session_state.get('screen_width', 768) > 1024:
            cols = st.columns(4)  # 4 columns for desktop
        
        for i, img_info in enumerate(current_images):
            with cols[i % len(cols)]:
                with st.container():
                    # Create a card-like container
                    card_html = f"""
                    <div class="image-container">
                        <div class="loading-placeholder" id="loading-{i}"></div>
                    </div>
                    """
                    placeholder = st.empty()
                    placeholder.markdown(card_html, unsafe_allow_html=True)
                    
                    # Load thumbnail
                    thumbnail = get_image_thumbnail(BUCKET_NAME, img_info['key'])
                    
                    if thumbnail:
                        placeholder.empty()
                        
                        # Display image
                        st.image(
                            f"data:image/jpeg;base64,{thumbnail}",
                            use_container_width=True
                        )
                        
                        # Image info
                        st.markdown(f"""
                        <div class="image-info">
                            <div class="image-filename">{img_info['filename']}</div>
                            <div class="image-details">
                                {img_info['size'] / 1024:.1f} KB • {img_info['last_modified'].strftime('%m/%d/%Y')}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Action buttons
                        col_view, col_download = st.columns(2)
                        
                        with col_view:
                            if st.button("👁️ View", key=f"view_{img_info['key']}", use_container_width=True):
                                # Load fullscreen image
                                with st.spinner("Loading fullscreen image..."):
                                    fullscreen_img = get_fullscreen_image(BUCKET_NAME, img_info['key'])
                                    if fullscreen_img:
                                        st.session_state.fullscreen_image = {
                                            'data': fullscreen_img,
                                            'filename': img_info['filename']
                                        }
                                        st.rerun()
                                    else:
                                        st.error("Could not load fullscreen image")
                        
                        with col_download:
                            if st.button("⬇️ Save", key=f"download_{img_info['key']}", use_container_width=True):
                                try:
                                    response = s3_client.get_object(Bucket=BUCKET_NAME, Key=img_info['key'])
                                    st.download_button(
                                        label="💾 Download",
                                        data=response['Body'].read(),
                                        file_name=img_info['filename'],
                                        mime='image/jpeg',
                                        use_container_width=True,
                                        key=f"dl_btn_{img_info['key']}"
                                    )
                                except ClientError as e:
                                    st.error(f"Download failed: {e}")
                    else:
                        placeholder.empty()
                        st.error(f"❌ Failed to load: {img_info['filename'][:20]}...")
                        st.caption(f"Size: {img_info['size'] / 1024:.1f} KB")

if __name__ == "__main__":
    main()