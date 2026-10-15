Feature: Granskningslogg över skick och ändringar
  Som användare som låter en LLM arbeta med mitt konto
  vill jag i efterhand kunna se vad som skickades och ändrades, och när,
  utan att loggen själv läcker innehållet i mina mejl eller lösenordet.
  Raden på stderr (som klienten ofta sparar i sin loggfil) har bara antalet
  mottagare; adresserna — även Bcc — finns bara i den uttryckliga granskningsfilen.

  Scenario: Ett skick loggas som en JSON-rad utan ämne, brödtext eller lösenord
    Given en SMTP-klient för ett konto utan begränsningar
    When koden skickar ett mejl till "anna@exempel.se" med ämnet "Hemligt ämne" och texten "Hemlig text"
    Then ska granskningsloggen ha en rad med åtgärden "send" och resultatet "ok"
    And ska raden ha antalet mottagare 1 men inte adressen "anna@exempel.se", och mejlets Message-ID
    And ska raden inte innehålla "Hemligt ämne", "Hemlig text" eller lösenordet

  Scenario: Ett vägrat skick loggas med resultatet fel
    Given en SMTP-klient för ett konto med inställningen "allowed_recipients" satt till "@exempel.se"
    When koden skickar ett mejl till "ond@annat.se" med ämnet "Hej" och texten "Hej"
    Then ska granskningsloggen ha en rad med åtgärden "send" och resultatet "error"
    And ska raden ha antalet mottagare 1 men inte adressen "ond@annat.se"

  Scenario: En flytt via ett verktyg loggas med verktyg, mapp och UID
    Given Bridge har mejlen med UID "5" i varje mapp
    When LLM:en flyttar UID "5" i "INBOX" till "Archive"
    Then ska granskningsloggen ha en rad med åtgärden "move_message" och resultatet "ok"
    And ska raden ha verktyget "move_email", mappen "INBOX" och UID:na "5"

  Scenario: En massflytt där ett mejl saknas loggas med vilka som lyckades
    Given Bridge har mejlen med UID "5" i varje mapp
    When koden flyttar UID:na "5,6" i "INBOX" till "Archive" med massflytt
    Then ska granskningsloggen ha en rad med åtgärden "move" och resultatet "error"
    And ska raden ange att UID "5" lyckades och UID "6" misslyckades

  Scenario: Ett verktyg som vägras av skrivskyddet loggas
    Given servern körs med inställningen "read_only" satt till "true"
    When LLM:en anropar verktyget "delete_email"
    Then ska granskningsloggen ha en rad med åtgärden "tool_call" och resultatet "error"
    And ska raden ha verktyget "delete_email"

  Scenario: Med PROTONMAIL_AUDIT_LOG skrivs raderna även till en fil som bara ägaren kan läsa
    Given granskningsloggen ska skrivas till en fil som inte finns än
    And en SMTP-klient för ett konto utan begränsningar
    When koden skickar ett mejl till "anna@exempel.se" med ämnet "Hej" och texten "Hej"
    Then ska filen ha rättigheterna 0600
    And ska filen innehålla en JSON-rad med åtgärden "send"
    And ska filens rad ha mottagarna "anna@exempel.se"

  Scenario: Granskningsloggen skrivs aldrig genom en symlänk
    Given granskningsloggen ska skrivas till en symlänk som pekar på en annan fil
    And en SMTP-klient för ett konto utan begränsningar
    When koden skickar ett mejl till "anna@exempel.se" med ämnet "Hej" och texten "Hej"
    Then ska mejlet ha skickats till "anna@exempel.se"
    And ska filen som symlänken pekar på vara orörd
    And ska en varning om granskningsloggen ha loggats
