import streamlit as st
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import base64
from io import BytesIO
from PIL import Image
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BUCKET_NAME = "sdh-saree-dhothi-ceremony"  # Replace with your bucket name
IMAGES_PER_PAGE = 8
MAX_IMAGE_SIZE = (300, 300)  # Thumbnail size for display

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

def paginate_images(images, page, per_page):
    """Paginate image list"""
    start = page * per_page
    end = start + per_page
    return images[start:end], len(images)

def main():
    st.set_page_config(
        page_title="SDH Saree Dhothi Ceremony Photo Browser",
        page_icon="📸",
        layout="wide"
    )
    
    st.title("📸 SDH Saree Dhothi Ceremony Photo Browser")
    
    # Check if environment variables are loaded
    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        st.error("⚠️ AWS credentials not found in environment variables!")
        st.info("Please ensure your .env file contains:\n- AWS_ACCESS_KEY_ID=your_access_key\n- AWS_SECRET_ACCESS_KEY=your_secret_key")
        return
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")
        # bucket_name = st.text_input("S3 Bucket Name", value=BUCKET_NAME)
        images_per_page = st.slider("Images per page", 6, 24, IMAGES_PER_PAGE)
        
        st.header("Navigation")
        
        # Debug info (remove in production)
        # if st.checkbox("Show debug info"):
            # st.write("AWS Access Key ID:", os.environ.get('AWS_ACCESS_KEY_ID', 'Not found')[:10] + "..." if os.environ.get('AWS_ACCESS_KEY_ID') else 'Not found')
            # st.write("AWS Secret Key:", "Found" if os.environ.get('AWS_SECRET_ACCESS_KEY') else 'Not found')
    
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
        breadcrumb = "Home"
        for i, part in enumerate(path_parts):
            if part:
                breadcrumb += f" > {part}"
        st.subheader(f"📁 {breadcrumb}")
        
        if st.button("⬆️ Back to Parent"):
            if st.session_state.path_history:
                st.session_state.current_path = st.session_state.path_history.pop()
            else:
                st.session_state.current_path = ""
            st.session_state.page = 0
            st.rerun()
    
    # List folders at current level
    folders = list_folders(s3_client, BUCKET_NAME, st.session_state.current_path)
    
    if folders:
        st.subheader("📂 Folders")
        cols = st.columns(min(4, len(folders)))
        
        for i, (folder_name, folder_path) in enumerate(folders):
            with cols[i % 4]:
                if st.button(f"📁 {folder_name}", key=f"folder_{i}"):
                    st.session_state.path_history.append(st.session_state.current_path)
                    st.session_state.current_path = folder_path
                    st.session_state.page = 0
                    st.rerun()
    
    # List and display images
    st.subheader("🖼️ Images")
    
    images = list_images(BUCKET_NAME, st.session_state.current_path)
    
    if not images:
        st.info("No images found in this folder.")
        return
    
    # Pagination
    current_images, total_images = paginate_images(
        images, st.session_state.page, images_per_page
    )
    
    # Pagination controls
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        total_pages = (total_images - 1) // images_per_page + 1
        st.write(f"Page {st.session_state.page + 1} of {total_pages} | {total_images} images total")
        
        col_prev, col_next = st.columns(2)
        with col_prev:
            if st.button("⬅️ Previous", disabled=st.session_state.page == 0):
                st.session_state.page = max(0, st.session_state.page - 1)
                st.rerun()
        
        with col_next:
            if st.button("➡️ Next", disabled=st.session_state.page >= total_pages - 1):
                st.session_state.page = min(total_pages - 1, st.session_state.page + 1)
                st.rerun()
    
    # Display images in grid
    if current_images:
        cols = st.columns(4)
        
        for i, img_info in enumerate(current_images):
            with cols[i % 4]:
                with st.container():
                    # Show loading placeholder
                    placeholder = st.empty()
                    placeholder.info(f"Loading {img_info['filename']}...")
                    
                    # Load thumbnail
                    thumbnail = get_image_thumbnail(BUCKET_NAME, img_info['key'])
                    
                    if thumbnail:
                        placeholder.empty()
                        st.image(
                            f"data:image/jpeg;base64,{thumbnail}",
                            caption=img_info['filename'],
                        )
                        
                        # Image info
                        st.caption(f"Size: {img_info['size'] / 1024:.1f} KB")
                        st.caption(f"Modified: {img_info['last_modified'].strftime('%Y-%m-%d')}")
                        
                        # Download button
                        if st.button(f"⬇️ Download", key=f"download_{i}"):
                            try:
                                response = s3_client.get_object(Bucket=BUCKET_NAME, Key=img_info['key'])
                                st.download_button(
                                    label="💾 Click to download",
                                    data=response['Body'].read(),
                                    file_name=img_info['filename'],
                                    mime='image/jpeg'
                                )
                            except ClientError as e:
                                st.error(f"Download failed: {e}")
                    else:
                        placeholder.empty()
                        st.error(f"❌ Cannot load: {img_info['filename']}")
                        st.caption(f"File may be corrupted or in unsupported format")
                        st.caption(f"Size: {img_info['size'] / 1024:.1f} KB")

if __name__ == "__main__":
    main()