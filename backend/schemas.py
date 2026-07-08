from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["Breakfast", "Lunch", "Dinner", "Desserts"]
Difficulty = Literal["Easy", "Medium", "Hard"]


class IngredientIn(BaseModel):
    name: str = Field(min_length=1)
    amount: Optional[str] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Ingredient name must not be empty")
        return v


class IngredientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    amount: Optional[str] = None


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order: int
    description: str


class RecipePayload(BaseModel):
    """JSON body of the multipart `data` field for create/update."""

    name: str = Field(min_length=1)
    category: Category
    cook_time_minutes: int = Field(ge=1)
    servings: int = Field(ge=1, default=2)
    difficulty: Difficulty = "Easy"
    ingredients: list[IngredientIn] = Field(min_length=1)
    steps: list[str] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def strip_recipe_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Recipe name must not be empty")
        return v

    @field_validator("steps")
    @classmethod
    def strip_steps(cls, v: list[str]) -> list[str]:
        cleaned = [s.strip() for s in v if s.strip()]
        if not cleaned:
            raise ValueError("At least one step is required")
        return cleaned


class RecipeListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: Category
    image_path: Optional[str] = None
    cook_time_minutes: int
    servings: int
    difficulty: Difficulty
    rating: Optional[float] = None
    times_cooked: int
    is_favorite: bool
    created_at: datetime


class RecipeDetail(RecipeListItem):
    updated_at: datetime
    ingredients: list[IngredientOut]
    steps: list[StepOut]


class RateBody(BaseModel):
    rating: float = Field(ge=1.0, le=5.0)


class FavoriteBody(BaseModel):
    is_favorite: bool


class CookResponse(BaseModel):
    times_cooked: int


class CatalogRecipe(BaseModel):
    index: int
    name: str
    category: Category
    image_path: Optional[str] = None
    cook_time_minutes: int
    servings: int
    difficulty: Difficulty
    ingredients_count: int
    in_cookbook: bool


class CatalogIngredient(BaseModel):
    name: str
    amount: Optional[str] = None


class RatedRecipe(BaseModel):
    id: int
    name: str
    image_path: Optional[str] = None
    rating: float


class StatsResponse(BaseModel):
    total_recipes: int
    recipes_cooked: int
    favorite_category: Optional[Category] = None
    average_rating: Optional[float] = None
    category_distribution: dict[str, int]
    recent_ratings: list[RatedRecipe]
