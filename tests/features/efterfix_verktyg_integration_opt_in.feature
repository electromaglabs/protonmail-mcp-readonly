Feature: Integrationstester körs bara när man ber om dem
  Som utvecklare som kör "uv run pytest" för att se att allt är grönt
  vill jag att tester mot riktiga Bridge bara körs när jag uttryckligen ber om det
  eftersom test_smtp.py skickar ett riktigt mejl när .env finns.

  Scenario: pytest utan filter samlar inte in integrationstester
    When jag samlar in testerna med "pytest"
    Then ska inget insamlat test ligga i tests/integration
    And ska enhetstester ha samlats in

  Scenario: pytest -m integration samlar in integrationstesterna
    When jag samlar in testerna med "pytest -m integration"
    Then ska tests/integration/test_smtp.py ha samlats in
    And ska inget insamlat test ligga utanför tests/integration
