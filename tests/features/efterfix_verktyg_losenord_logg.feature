Feature: Bridge-lösenordet hamnar aldrig i loggen vid felkonfiguration
  Som användare som kör servern i Claude Desktop
  vill jag att ett konfigurationsfel inte skriver lösenordet i klartext
  eftersom stderr sparas i en loggfil på disken.

  Scenario: Användarnamnet saknas men lösenordet är satt
    Given att PROTONMAIL_PASSWORD är "HEMLIGT-bridge-losen" och PROTONMAIL_USERNAME saknas
    When servern startar
    Then ska starten misslyckas med ett konfigurationsfel som nämner "username"
    And ska loggen inte innehålla "HEMLIGT-bridge-losen"
    And ska felmeddelandet inte innehålla "HEMLIGT-bridge-losen"
