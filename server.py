import os
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pymongo import MongoClient
import shutil
from pathlib import Path

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://puffarchive.netlify.app", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017/')
db_name = os.environ.get('DB_NAME', 'puff_archive')
client = MongoClient(mongo_url)
db = client[db_name]
cheats_collection = db.cheats

# Create uploads directory
upload_dir = Path("/app/backend/uploads")
upload_dir.mkdir(exist_ok=True)

# Serve static files
app.mount("/api/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")

# Security
security = HTTPBearer()
ADMIN_CODE = "201016"

# Models
class CheatCreate(BaseModel):
    name: str
    description: str
    link: str
    youtube_url: Optional[str] = None
    thumbnail_url: Optional[str] = None

class CheatResponse(BaseModel):
    id: str
    name: str
    description: str
    link: str
    youtube_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    created_at: str

class AuthRequest(BaseModel):
    code: str

class AuthResponse(BaseModel):
    success: bool
    token: str

# Auth functions
def verify_admin_code(code: str) -> bool:
    return code == ADMIN_CODE

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != ADMIN_CODE:
        raise HTTPException(status_code=401, detail="Invalid authentication code")
    return True

# Routes
@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/api/auth", response_model=AuthResponse)
async def authenticate(auth_request: AuthRequest):
    if verify_admin_code(auth_request.code):
        return AuthResponse(success=True, token=ADMIN_CODE)
    else:
        raise HTTPException(status_code=401, detail="Invalid authentication code")

@app.get("/api/cheats", response_model=List[CheatResponse])
async def get_cheats():
    cheats = list(cheats_collection.find())
    return [
        CheatResponse(
            id=cheat["id"],
            name=cheat["name"],
            description=cheat["description"],
            link=cheat["link"],
            youtube_url=cheat.get("youtube_url"),
            thumbnail_url=cheat.get("thumbnail_url"),
            created_at=cheat["created_at"]
        )
        for cheat in cheats
    ]

@app.post("/api/cheats", response_model=CheatResponse)
async def create_cheat(cheat: CheatCreate, _: bool = Depends(get_current_user)):
    cheat_id = str(uuid.uuid4())
    cheat_data = {
        "id": cheat_id,
        "name": cheat.name,
        "description": cheat.description,
        "link": cheat.link,
        "youtube_url": cheat.youtube_url,
        "thumbnail_url": cheat.thumbnail_url,
        "created_at": datetime.now().isoformat()
    }
    
    cheats_collection.insert_one(cheat_data)
    
    return CheatResponse(**cheat_data)

@app.delete("/api/cheats/{cheat_id}")
async def delete_cheat(cheat_id: str, _: bool = Depends(get_current_user)):
    result = cheats_collection.delete_one({"id": cheat_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cheat not found")
    return {"message": "Cheat deleted successfully"}

@app.post("/api/upload")
async def upload_thumbnail(file: UploadFile = File(...), _: bool = Depends(get_current_user)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Generate unique filename
    file_extension = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    file_path = upload_dir / unique_filename
    
    # Save file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Return URL
    thumbnail_url = f"/api/uploads/{unique_filename}"
    return {"thumbnail_url": thumbnail_url}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
