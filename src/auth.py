from dotenv import load_dotenv
from fastapi import HTTPException, Header, status
import os

# Carregar variáveis do ficheiro .env
load_dotenv()

# Ler variáveis
ENV = os.environ.get("ENV", "dev").lower()
ENDPOINT_API_KEY = os.environ.get("ENDPOINT_API_KEY")

# Se estiver em produção e a variável não existir, lançar erro
if ENV == "prod" and not ENDPOINT_API_KEY:
    raise RuntimeError("ENDPOINT_API_KEY environment variable is not set")

def verify_token(authorization: str = Header(None)):
    """
    Verifica o token Bearer em modo produção.
    Ignora verificação em modo desenvolvimento (ENV=dev).
    """

    # 🚧 Em modo desenvolvimento, ignora a verificação (para evitar bloqueios locais)
    if ENV == "dev":
        return True

    # ✅ Em modo produção, exige cabeçalho Authorization
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing"
        )

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format"
        )

    token = parts[1]
    if token != ENDPOINT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token"
        )

    return True
