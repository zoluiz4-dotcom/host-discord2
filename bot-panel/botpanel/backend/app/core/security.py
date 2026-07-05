"""
Segurança do painel.

O painel não tem tela de login, mas isso NÃO significa que o backend
fica aberto. Toda requisição (exceto o healthcheck) precisa trazer o
header `X-API-Key` com o valor definido em PANEL_API_KEY no .env.

O frontend guarda essa chave no localStorage do navegador e a envia
automaticamente — o usuário só digita a chave uma vez, na primeira
vez que abre o painel, e nunca mais vê nada parecido com login.
"""
import hmac

from fastapi import Header, HTTPException, Query, status

from app.core.config import settings


async def require_api_key(
    x_api_key: str = Header(default=""),
    api_key: str = Query(default=""),
) -> None:
    """
    Aceita a chave tanto no header X-API-Key (usado por todas as chamadas
    normais feitas via JavaScript) quanto na query string `api_key` (usado
    apenas por downloads via link direto, onde não é possível definir
    headers customizados).
    """
    provided = x_api_key or api_key
    if not provided or not hmac.compare_digest(provided, settings.PANEL_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de API inválida ou ausente.",
        )
