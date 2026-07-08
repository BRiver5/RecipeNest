from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import relationship

from database import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)  # "Breakfast" | "Lunch" | "Dinner" | "Desserts"
    image_path = Column(String, nullable=True)  # relative path under /static/recipe_images/
    cook_time_minutes = Column(Integer, nullable=False)
    servings = Column(Integer, nullable=False, default=2)
    difficulty = Column(String, nullable=False, default="Easy")  # "Easy" | "Medium" | "Hard"
    rating = Column(Float, nullable=True)  # 1.0 - 5.0, null until rated
    rated_at = Column(DateTime, nullable=True)
    times_cooked = Column(Integer, nullable=False, default=0)
    is_favorite = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    ingredients = relationship(
        "Ingredient", back_populates="recipe", cascade="all, delete-orphan"
    )
    steps = relationship(
        "Step",
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="Step.order",
    )


class SeededDevice(Base):
    """Devices that already received the built-in starter catalog."""

    __tablename__ = "seeded_devices"

    device_id = Column(String, primary_key=True)


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    name = Column(String, nullable=False)
    amount = Column(String, nullable=True)

    recipe = relationship("Recipe", back_populates="ingredients")


class Step(Base):
    __tablename__ = "steps"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    order = Column(Integer, nullable=False)
    description = Column(String, nullable=False)

    recipe = relationship("Recipe", back_populates="steps")
