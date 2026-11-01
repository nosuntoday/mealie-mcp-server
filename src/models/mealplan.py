from datetime import date as Date
from datetime import timedelta
from typing import Annotated, Literal, Optional, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Value cannot be blank")
    return value


def iso_date(value: str) -> str:
    Date.fromisoformat(value)
    return value


Identifier = Annotated[str, AfterValidator(nonblank)]
ISODate = Annotated[
    str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$"), AfterValidator(iso_date)
]
EntryType = Literal["breakfast", "lunch", "dinner", "side"]


class MealPlanEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: ISODate
    end_date: Optional[ISODate] = None
    recipe_id: Optional[Identifier] = None
    title: Optional[str] = None
    entry_type: EntryType = "breakfast"

    @model_validator(mode="after")
    def require_recipe_or_title(self) -> Self:
        if not self.recipe_id and not (self.title and self.title.strip()):
            raise ValueError("Either recipe_id or title must be provided")
        if self.end_date is not None:
            if Date.fromisoformat(self.end_date) - Date.fromisoformat(
                self.date
            ) != timedelta(days=6):
                raise ValueError(
                    "A weekly plan must end exactly six days after its start"
                )
        return self


class MealPlanUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    date: Optional[ISODate] = None
    end_date: Optional[ISODate] = Field(default=None, alias="endDate")
    recipe_id: Optional[Identifier] = Field(default=None, alias="recipeId")
    title: Optional[str] = None
    entry_type: Optional[EntryType] = Field(default=None, alias="entryType")

    @model_validator(mode="after")
    def require_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided to update")
        for name in ("date", "title", "entry_type"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError("Only recipe_id can be cleared with null")
        return self


class MealPlanDateRange(BaseModel):
    start_date: Optional[ISODate] = None
    end_date: Optional[ISODate] = None

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Start date must not follow end date")
        return self
