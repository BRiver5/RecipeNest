import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import case, func
from sqlalchemy.orm import Session, selectinload

import models
import schemas
from database import BASE_DIR, Base, engine, get_db
from seed_data import SEED_RECIPES

Base.metadata.create_all(bind=engine)

STATIC_DIR = BASE_DIR / "static"
IMAGES_DIR = STATIC_DIR / "recipe_images"
SEED_IMAGES_DIR = IMAGES_DIR / "seed"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024

CATEGORIES = ["Breakfast", "Lunch", "Dinner", "Desserts"]

app = FastAPI(title="RecipeNest API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_device_id(x_device_id: Optional[str] = Header(default=None)) -> str:
    if not x_device_id or not x_device_id.strip():
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    return x_device_id.strip()


def get_owned_recipe(recipe_id: int, device_id: str, db: Session) -> models.Recipe:
    recipe = (
        db.query(models.Recipe)
        .options(
            selectinload(models.Recipe.ingredients),
            selectinload(models.Recipe.steps),
        )
        .filter(models.Recipe.id == recipe_id, models.Recipe.device_id == device_id)
        .first()
    )
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


def parse_payload(data: str) -> schemas.RecipePayload:
    try:
        return schemas.RecipePayload.model_validate_json(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


async def save_image(image: UploadFile) -> str:
    ext = ALLOWED_IMAGE_TYPES.get(image.content_type or "")
    if ext is None:
        raise HTTPException(
            status_code=422,
            detail="Unsupported image type; use JPEG, PNG or WebP",
        )
    contents = await image.read()
    if len(contents) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="Image is larger than 10 MB")
    filename = f"{uuid.uuid4().hex}{ext}"
    (IMAGES_DIR / filename).write_bytes(contents)
    return f"/static/recipe_images/{filename}"


def delete_image_file(image_path: Optional[str]) -> None:
    if not image_path:
        return
    candidate = (BASE_DIR / image_path.lstrip("/")).resolve()
    # Seed images are shared between devices — never delete them.
    if candidate.is_relative_to(SEED_IMAGES_DIR.resolve()):
        return
    if candidate.is_relative_to(IMAGES_DIR.resolve()) and candidate.is_file():
        candidate.unlink()


def seed_image_path(entry: dict) -> Optional[str]:
    image_name = entry.get("image")
    if image_name and (SEED_IMAGES_DIR / image_name).is_file():
        return f"/static/recipe_images/seed/{image_name}"
    return None


def build_seed_recipe(entry: dict, device_id: str) -> models.Recipe:
    recipe = models.Recipe(
        device_id=device_id,
        name=entry["name"],
        category=entry["category"],
        image_path=seed_image_path(entry),
        cook_time_minutes=entry["cook_time_minutes"],
        servings=entry["servings"],
        difficulty=entry["difficulty"],
    )
    for name, amount in entry["ingredients"]:
        recipe.ingredients.append(models.Ingredient(name=name, amount=amount))
    for index, description in enumerate(entry["steps"], start=1):
        recipe.steps.append(models.Step(order=index, description=description))
    return recipe


def ensure_seeded(device_id: str, db: Session) -> None:
    """Copy the built-in starter catalog into a device's cookbook once."""
    already = db.get(models.SeededDevice, device_id)
    if already is not None:
        return
    for entry in SEED_RECIPES:
        db.add(build_seed_recipe(entry, device_id))
    db.add(models.SeededDevice(device_id=device_id))
    db.commit()


def replace_children(
    db: Session, recipe: models.Recipe, payload: schemas.RecipePayload
) -> None:
    recipe.ingredients.clear()
    recipe.steps.clear()
    db.flush()
    for ingredient in payload.ingredients:
        recipe.ingredients.append(
            models.Ingredient(name=ingredient.name, amount=ingredient.amount)
        )
    for index, description in enumerate(payload.steps, start=1):
        recipe.steps.append(models.Step(order=index, description=description))


@app.get("/api/recipes", response_model=list[schemas.RecipeListItem])
def list_recipes(
    category: Optional[str] = None,
    q: Optional[str] = None,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    ensure_seeded(device_id, db)
    query = db.query(models.Recipe).filter(models.Recipe.device_id == device_id)
    if category and category in CATEGORIES:
        query = query.filter(models.Recipe.category == category)
    if q and q.strip():
        query = query.filter(models.Recipe.name.ilike(f"%{q.strip()}%"))
    return query.order_by(models.Recipe.created_at.desc(), models.Recipe.id.desc()).all()


@app.post("/api/recipes", response_model=schemas.RecipeDetail, status_code=201)
async def create_recipe(
    data: str = Form(...),
    image: Optional[UploadFile] = File(default=None),
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    payload = parse_payload(data)
    image_path = await save_image(image) if image is not None else None

    recipe = models.Recipe(
        device_id=device_id,
        name=payload.name,
        category=payload.category,
        image_path=image_path,
        cook_time_minutes=payload.cook_time_minutes,
        servings=payload.servings,
        difficulty=payload.difficulty,
    )
    for ingredient in payload.ingredients:
        recipe.ingredients.append(
            models.Ingredient(name=ingredient.name, amount=ingredient.amount)
        )
    for index, description in enumerate(payload.steps, start=1):
        recipe.steps.append(models.Step(order=index, description=description))

    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


@app.get("/api/recipes/{recipe_id}", response_model=schemas.RecipeDetail)
def get_recipe(
    recipe_id: int,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    return get_owned_recipe(recipe_id, device_id, db)


@app.put("/api/recipes/{recipe_id}", response_model=schemas.RecipeDetail)
async def update_recipe(
    recipe_id: int,
    data: str = Form(...),
    image: Optional[UploadFile] = File(default=None),
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    recipe = get_owned_recipe(recipe_id, device_id, db)
    payload = parse_payload(data)

    if image is not None:
        new_path = await save_image(image)
        delete_image_file(recipe.image_path)
        recipe.image_path = new_path

    recipe.name = payload.name
    recipe.category = payload.category
    recipe.cook_time_minutes = payload.cook_time_minutes
    recipe.servings = payload.servings
    recipe.difficulty = payload.difficulty
    replace_children(db, recipe, payload)

    db.commit()
    db.refresh(recipe)
    return recipe


@app.delete("/api/recipes/{recipe_id}", status_code=204)
def delete_recipe(
    recipe_id: int,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    recipe = get_owned_recipe(recipe_id, device_id, db)
    image_path = recipe.image_path
    db.delete(recipe)
    db.commit()
    delete_image_file(image_path)


@app.post("/api/recipes/{recipe_id}/rate", response_model=schemas.RecipeDetail)
def rate_recipe(
    recipe_id: int,
    body: schemas.RateBody,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    recipe = get_owned_recipe(recipe_id, device_id, db)
    recipe.rating = body.rating
    recipe.rated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(recipe)
    return recipe


@app.post("/api/recipes/{recipe_id}/cook", response_model=schemas.CookResponse)
def cook_recipe(
    recipe_id: int,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    recipe = get_owned_recipe(recipe_id, device_id, db)
    recipe.times_cooked += 1
    db.commit()
    return schemas.CookResponse(times_cooked=recipe.times_cooked)


@app.post("/api/recipes/{recipe_id}/favorite", response_model=schemas.RecipeDetail)
def favorite_recipe(
    recipe_id: int,
    body: schemas.FavoriteBody,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    recipe = get_owned_recipe(recipe_id, device_id, db)
    recipe.is_favorite = body.is_favorite
    db.commit()
    db.refresh(recipe)
    return recipe


@app.get("/api/catalog/recipes", response_model=list[schemas.CatalogRecipe])
def catalog_recipes(
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    ensure_seeded(device_id, db)
    existing_names = {
        name
        for (name,) in db.query(models.Recipe.name)
        .filter(models.Recipe.device_id == device_id)
        .all()
    }
    return [
        schemas.CatalogRecipe(
            index=index,
            name=entry["name"],
            category=entry["category"],
            image_path=seed_image_path(entry),
            cook_time_minutes=entry["cook_time_minutes"],
            servings=entry["servings"],
            difficulty=entry["difficulty"],
            ingredients_count=len(entry["ingredients"]),
            in_cookbook=entry["name"] in existing_names,
        )
        for index, entry in enumerate(SEED_RECIPES, start=1)
    ]


@app.post(
    "/api/catalog/recipes/{index}/add",
    response_model=schemas.RecipeDetail,
    status_code=201,
)
def add_catalog_recipe(
    index: int,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    if not 1 <= index <= len(SEED_RECIPES):
        raise HTTPException(status_code=404, detail="Catalog recipe not found")
    recipe = build_seed_recipe(SEED_RECIPES[index - 1], device_id)
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


@app.get("/api/catalog/ingredients", response_model=list[schemas.CatalogIngredient])
def catalog_ingredients(device_id: str = Depends(get_device_id)):
    seen: dict[str, Optional[str]] = {}
    for entry in SEED_RECIPES:
        for name, amount in entry["ingredients"]:
            seen.setdefault(name, amount)
    return [
        schemas.CatalogIngredient(name=name, amount=amount)
        for name, amount in sorted(seen.items(), key=lambda item: item[0].lower())
    ]


@app.get("/api/stats", response_model=schemas.StatsResponse)
def get_stats(
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    ensure_seeded(device_id, db)
    base = db.query(models.Recipe).filter(models.Recipe.device_id == device_id)

    totals = db.query(
        func.count(models.Recipe.id),
        func.sum(case((models.Recipe.times_cooked > 0, 1), else_=0)),
        func.avg(models.Recipe.rating),
    ).filter(models.Recipe.device_id == device_id).one()
    total_recipes = totals[0] or 0
    recipes_cooked = totals[1] or 0
    average_rating = round(totals[2], 1) if totals[2] is not None else None

    distribution_rows = (
        db.query(models.Recipe.category, func.count(models.Recipe.id))
        .filter(models.Recipe.device_id == device_id)
        .group_by(models.Recipe.category)
        .all()
    )
    category_distribution = {category: 0 for category in CATEGORIES}
    for category, count in distribution_rows:
        if category in category_distribution:
            category_distribution[category] = count

    favorite_category = None
    max_count = max(category_distribution.values(), default=0)
    if max_count > 0:
        favorite_category = sorted(
            category
            for category, count in category_distribution.items()
            if count == max_count
        )[0]

    rated = (
        base.filter(models.Recipe.rating.isnot(None))
        .order_by(models.Recipe.rated_at.desc(), models.Recipe.id.desc())
        .limit(10)
        .all()
    )
    recent_ratings = [
        schemas.RatedRecipe(
            id=recipe.id,
            name=recipe.name,
            image_path=recipe.image_path,
            rating=recipe.rating,
        )
        for recipe in rated
    ]

    return schemas.StatsResponse(
        total_recipes=total_recipes,
        recipes_cooked=recipes_cooked,
        favorite_category=favorite_category,
        average_rating=average_rating,
        category_distribution=category_distribution,
        recent_ratings=recent_ratings,
    )
