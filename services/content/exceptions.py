from fastapi import HTTPException

class AuthException(HTTPException):
    def __init__(self, detail: str = "Missing user identity headers from gateway"):
        super().__init__(status_code=401, detail=detail)

class InvalidFileException(HTTPException):
    def __init__(self, detail: str = "Invalid JSON file"):
        super().__init__(status_code=400, detail=detail)

class FileReadException(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=400, detail=f"Could not read file: {detail}")

class UploadFailedException(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=500, detail=f"Upload failed: {detail}")

class FileUploadFailedException(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=500, detail=f"File upload failed: {detail}")
