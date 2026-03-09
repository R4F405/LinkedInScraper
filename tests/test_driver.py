from unittest.mock import patch, MagicMock
from scraper.driver import create_driver, quit_driver


@patch("scraper.driver.ChromeDriverManager")
@patch("scraper.driver.webdriver.Chrome")
def test_create_driver_devuelve_instancia(mock_chrome, mock_manager):
    mock_manager.return_value.install.return_value = "/fake/path"
    mock_chrome.return_value = MagicMock()

    driver = create_driver(headless=True)
    assert driver is not None


def test_quit_driver_con_none_no_explota():
    quit_driver(None)  # No debe lanzar ningún error


def test_quit_driver_llama_a_quit():
    mock_driver = MagicMock()
    quit_driver(mock_driver)
    mock_driver.quit.assert_called_once()