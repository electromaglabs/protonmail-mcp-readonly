Feature: En adress som inte går att bygga ett mejl av ger ett begripligt fel utan läcka
  Som användare som låter en LLM skicka med hemlig kopia
  vill jag att en trasig adress ger felet "Ogiltig e-postadress"
  och att den hemliga adressen inte skrivs i serverns logg (stderr) som ett stackspår.

  Scenario: En trasig Bcc-adress vägras som ogiltig, utan stackspår i loggen
    Given en SMTP-klient för ett konto utan begränsningar
    When LLM:en skickar ett mejl till "a@b.se" med hemlig kopia '"<hemlig.chef\"@firma.se'
    Then ska anropet vägras med ett fel som nämner "Ogiltig e-postadress"
    And ska felet inte vara ett oväntat fel
    And ska serverns logg inte innehålla "hemlig.chef"
    And ska Bridge inte ha kontaktats

  Scenario: Ett utkast med en trasig Bcc-adress sparas inte
    Given en SMTP-klient för ett konto utan begränsningar
    When LLM:en skapar ett utkast till "a@b.se" med hemlig kopia '"<hemlig.chef\"@firma.se'
    Then ska anropet vägras med ett fel som nämner "Ogiltig e-postadress"
    And ska serverns logg inte innehålla "hemlig.chef"
    And ska Bridge inte ha kontaktats
