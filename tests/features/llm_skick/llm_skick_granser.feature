Feature: Gränser för antal mottagare och skick per timme
  Som användare som låter en LLM skicka e-post åt mig
  vill jag att antalet mottagare per mejl och antalet skick per timme är begränsat
  så att en skenande loop eller en promptinjektion inte kan göra massutskick.

  Scenario: Ett mejl till fler mottagare än gränsen vägras
    Given en SMTP-klient för ett konto med inställningen "max_recipients" satt till "3"
    When koden skickar ett mejl till 4 olika mottagare
    Then ska anropet vägras med ett fel som nämner "PROTONMAIL_MAX_RECIPIENTS"
    And ska felet nämna "4 mottagare"
    And ska Bridge inte ha kontaktats

  Scenario: Ett mejl till precis så många mottagare som gränsen skickas
    Given en SMTP-klient för ett konto med inställningen "max_recipients" satt till "3"
    When koden skickar ett mejl till 3 olika mottagare
    Then ska verktyget svara utan fel

  Scenario: Standardgränsen är 50 mottagare per mejl
    Given en SMTP-klient för ett konto utan begränsningar
    When koden skickar ett mejl till 51 olika mottagare
    Then ska anropet vägras med ett fel som nämner "högst 50"

  Scenario: När timgränsen är nådd vägras nästa skick och felet säger när det går igen
    Given en SMTP-klient för ett konto med inställningen "max_sends_per_hour" satt till "2"
    When koden skickar 2 mejl i rad
    And det går 10 minuter
    And koden skickar ett mejl till "anna@exempel.se"
    Then ska anropet vägras med ett fel som nämner "PROTONMAIL_MAX_SENDS_PER_HOUR"
    And ska felet nämna "om 50 minuter"
    And ska bara 2 mejl ha skickats

  Scenario: Gränsen glider — en timme efter det första skicket går det igen
    Given en SMTP-klient för ett konto med inställningen "max_sends_per_hour" satt till "2"
    When koden skickar 2 mejl i rad
    And det går 61 minuter
    And koden skickar ett mejl till "anna@exempel.se"
    Then ska verktyget svara utan fel
    And ska bara 3 mejl ha skickats

  Scenario: Ett vägrat skick räknas inte mot timgränsen
    Given en SMTP-klient för ett konto med inställningen "max_sends_per_hour" satt till "1"
    And inställningen "allowed_recipients" är satt till "@exempel.se"
    When koden skickar ett mejl till "ond@annat.se"
    And koden skickar ett mejl till "anna@exempel.se"
    Then ska verktyget svara utan fel
    And ska bara 1 mejl ha skickats
