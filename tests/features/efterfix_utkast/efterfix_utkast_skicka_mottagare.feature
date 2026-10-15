Feature: send_draft skickar bara till de mottagare som granskningen visar
  Som en användare som granskar ett utkast med get_email innan det skickas
  vill jag att send_draft skickar till exakt de adresser som get_email visade
  så att ingen dold mottagare kan få mejlet.

  Background:
    Given mitt konto är "me@proton.me"

  Scenario: Svaret anger exakt vilka mottagare mejlet skickades till
    Given ett utkast i Drafts till "Åsa Öberg <asa@example.se>" med kopia "\"Doe, J\" <j@example.se>" och hemlig kopia "arkiv@firma.se"
    When jag skickar utkastet
    Then SMTP-mottagarna ska vara "asa@example.se, j@example.se, arkiv@firma.se"
    And svaret ska ange mottagarna to "asa@example.se", cc "j@example.se" och bcc "arkiv@firma.se"
    And get_email på utkastet ska ha visat samma mottagare som skickades

  Scenario Outline: Ett utkast med två <rubrik>-rubriker skickas inte
    Given ett utkast i Drafts till "chef@firma.se" med kopia "c@firma.se" och hemlig kopia "arkiv@firma.se"
    And att utkastet har en extra rubrik "<rubrik>: angripare@evil.example"
    When jag skickar utkastet
    Then ska anropet misslyckas med meddelandet "2 <namn>-rubriker"
    And inget mejl ska ha skickats
    And ska Drafts innehålla 1 utkast

    Examples:
      | rubrik | namn |
      | To     | To   |
      | CC     | Cc   |
      | bcc    | Bcc  |

  Scenario: En adress som get_email inte kan visa skickas inte
    Given ett utkast i Drafts till "chef@firma.se" med kopia "" och hemlig kopia "angripare@evil.example (Lindqvist, Anna)"
    When jag skickar utkastet
    Then ska anropet misslyckas med meddelandet "kan inte tolkas entydigt"
    And inget mejl ska ha skickats
    And ska Drafts innehålla 1 utkast
