Feature: Tydligt fel när ett brev inte finns
  Som en MCP-klient
  vill jag få ett felmeddelande som säger att brevet inte finns
  i stället för ett tomt svar som ser ut som att ingenting hände.

  Scenario: Hämta ett brev med ett UID som inte finns
    Given att mappen "Archive" inte har något brev med UID "999"
    When jag anropar get_email med uid "999" i mappen "Archive"
    Then ska anropet misslyckas med meddelandet "Inget meddelande med UID 999 i Archive"

  Scenario: Hämta headers för ett UID som inte finns
    Given att mappen "INBOX" inte har något brev med UID "999"
    When jag anropar get_email_headers med uid "999" i mappen "INBOX"
    Then ska anropet misslyckas med meddelandet "Inget meddelande med UID 999 i INBOX"
