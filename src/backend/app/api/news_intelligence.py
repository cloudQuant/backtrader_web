import typing

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.database import get_db
from app.services.news_intelligence import get_news_intelligence_service

router = APIRouter(prefix="/news-intelligence", tags=["News Intelligence"])


@router.post("/sources", status_code=status.HTTP_201_CREATED, response_model=None)
async def create_source(
    payload: dict,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    return await get_news_intelligence_service(db).add_source(current_user.sub, payload)


@router.post("/articles/ingest", response_model=None)
async def ingest_articles(
    payload: dict,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    return await get_news_intelligence_service(db).ingest(
        current_user.sub,
        list(payload.get("articles") or []),
    )


@router.post("/sources/{source_name}/pull", response_model=None)
async def pull_source(
    source_name: str,
    limit: int = 20,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    result = await get_news_intelligence_service(db).pull_source(
        current_user.sub,
        source_name,
        limit=limit,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source_not_found")
    return result


@router.get("/articles", response_model=None)
async def list_articles(
    sentiment: str | None = None,
    source: str | None = None,
    ticker: str | None = None,
    cluster_id: str | None = None,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    return await get_news_intelligence_service(db).list_articles(
        current_user.sub,
        sentiment=sentiment,
        source=source,
        ticker=ticker,
        cluster_id=cluster_id,
    )


@router.get("/articles/{article_id}/content", response_model=None)
async def get_article_content(
    article_id: str,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    """Return content saved during RSS/manual article ingestion."""
    article = await get_news_intelligence_service(db).get_article_content(
        current_user.sub,
        article_id,
    )
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="article_not_found")
    return article


@router.post("/analyze", response_model=None)
async def analyze(
    payload: dict,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    return await get_news_intelligence_service(db).analyze_headline(
        current_user.sub,
        str(payload.get("headline") or ""),
        allow_ai=bool(payload.get("allow_ai")),
    )
