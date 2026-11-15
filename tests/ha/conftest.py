import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components.

    The recorder has to be requested before anything that creates hass.
    """
    yield
