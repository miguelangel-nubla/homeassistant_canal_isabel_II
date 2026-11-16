from unittest.mock import PropertyMock, patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components.

    The recorder has to be requested before anything that creates hass.
    """
    yield


@pytest.fixture
def entity_registry_enabled_by_default():
    """Create the entities that are off by default as if they were on."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        new_callable=PropertyMock(return_value=True),
    ):
        yield
