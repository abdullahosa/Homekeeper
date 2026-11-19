"""One to-do list per module: what needs doing now."""

from __future__ import annotations

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .entity import HomekeeperEntity
from .runtime import Runtime, get_runtime


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    runtime = get_runtime(hass, entry.entry_id)
    async_add_entities(
        HomekeeperTodo(runtime, module_id) for module_id in runtime.engine.modules
    )


class HomekeeperTodo(HomekeeperEntity, TodoListEntity):
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(self, runtime: Runtime, module_id: str) -> None:
        super().__init__(runtime)
        self._module_id = module_id
        module = runtime.engine.modules[module_id]
        self._attr_unique_id = f"{runtime.entry.entry_id}_{module_id}_todo"
        self._attr_name = module.title.get("en") or module_id

    @property
    def todo_items(self) -> list[TodoItem]:
        eng = self.runtime.engine
        today = dt_util.now().date()
        items = []
        for duty, occ, state in eng.open_items(today):
            if duty.module != self._module_id:
                continue
            owners = ", ".join(
                eng.people[o].name for o in eng.effective_owners(duty)
            )
            items.append(
                TodoItem(
                    uid=duty.id,
                    summary=duty.display_title("en"),
                    status=TodoItemStatus.NEEDS_ACTION,
                    due=occ.due,
                    description="\n".join(
                        p
                        for p in (
                            f"Owner: {owners}" if owners else "",
                            "Snoozed" if state == "snoozed" else "",
                            duty.how_to,
                            *eng.login_lines(duty),
                        )
                        if p
                    ),
                )
            )
        return items

    async def async_update_todo_item(self, item: TodoItem) -> None:
        if item.status != TodoItemStatus.COMPLETED:
            return
        eng = self.runtime.engine
        try:
            result = eng.complete(str(item.uid), None, dt_util.now(), "button")
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        await self.runtime._dispatch(result, dt_util.now())
