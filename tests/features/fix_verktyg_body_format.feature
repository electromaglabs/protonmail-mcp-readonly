Feature: Giltiga format och längder när ett brev hämtas
  Som en MCP-klient
  vill jag att get_email bara accepterar de format och längder som verktyget kan leverera
  så att jag får ett tydligt fel i stället för ett otrunkerat eller felräknat svar.

  Scenario: Ett okänt body_format avvisas
    Given att brevet med UID "456" finns i INBOX
    When jag hämtar brevet med body_format "html"
    Then ska anropet avvisas med ett valideringsfel om "body_format"

  Scenario: Formatnamn är skiftlägeskänsliga
    Given att brevet med UID "456" finns i INBOX
    When jag hämtar brevet med body_format "TEXT"
    Then ska anropet avvisas med ett valideringsfel om "body_format"

  Scenario: En negativ maxlängd avvisas
    Given att brevet med UID "456" finns i INBOX
    When jag hämtar brevet med max_length -5
    Then ska anropet avvisas med ett valideringsfel om "max_length"

  Scenario: Formatet stripped med maxlängd noll accepteras
    Given att brevet med UID "456" finns i INBOX
    When jag hämtar brevet med body_format "stripped" och max_length 0
    Then ska brevet returneras med ämnesraden "Test subject"
