Feature: Skicka ett godkänt utkast
  Som en användare som har granskat ett utkast
  vill jag kunna be Claude skicka just det utkastet
  så att mottagarna får exakt det jag godkände och utkastet försvinner ur Drafts.

  Background:
    Given mitt konto är "me@proton.me"

  Scenario: Utkastet skickas till alla mottagare och tas bort ur Drafts
    Given ett utkast skapat till "Åsa Öberg <asa@example.se>" med kopia till "cc@example.se" och hemlig kopia till "hemlig@example.se"
    When jag skickar utkastet
    Then SMTP-mottagarna ska vara "asa@example.se, cc@example.se, hemlig@example.se"
    And det skickade mejlet ska sakna headern "Bcc"
    And det skickade mejlet ska ha utkastets ämne, text och Message-ID
    And ska Drafts innehålla 0 utkast
    And svaret ska ange att mejlet skickades och att utkastet togs bort

  Scenario: Misslyckas skicket ligger utkastet kvar
    Given ett utkast skapat till "asa@example.se" med kopia till "cc@example.se" och hemlig kopia till "hemlig@example.se"
    And att SMTP-servern vägrar alla mottagare
    When jag skickar utkastet
    Then ska anropet misslyckas
    And ska Drafts innehålla 1 utkast
    And inget UID STORE eller UID EXPUNGE ska ha skickats

  Scenario: Vägrar servern bara några mottagare ligger utkastet kvar och felet säger vilka
    Given ett utkast skapat till "asa@example.se" med kopia till "cc@example.se" och hemlig kopia till "hemlig@example.se"
    And att SMTP-servern vägrar "cc@example.se"
    When jag skickar utkastet
    Then ska anropet misslyckas med meddelandet "vägrade 1"
    And ska Drafts innehålla 1 utkast

  Scenario: Går utkastet inte att ta bort efter skicket sägs det tydligt
    Given ett utkast skapat till "asa@example.se" med kopia till "cc@example.se" och hemlig kopia till "hemlig@example.se"
    And att Bridge svarar NO på "EXPUNGE"
    When jag skickar utkastet
    Then SMTP-mottagarna ska vara "asa@example.se, cc@example.se, hemlig@example.se"
    And svaret ska ange att mejlet skickades men att utkastet ligger kvar

  Scenario: Ett utkast som inte finns kan inte skickas
    When jag skickar utkastet med UID "999"
    Then ska anropet misslyckas med meddelandet "Inget utkast med UID 999 i Drafts"
    And inget mejl ska ha skickats

  Scenario: Ett utkast utan mottagare skickas inte
    Given ett utkast i Drafts utan mottagare
    When jag skickar utkastet
    Then ska anropet misslyckas med meddelandet "saknar mottagare"
    And inget mejl ska ha skickats
    And ska Drafts innehålla 1 utkast
