Feature: Ogiltiga argument avvisas innan Bridge kontaktas
  Som användare av ett läsverktyg
  vill jag att ett ogiltigt mappnamn eller UID stoppas innan något skickas,
  så att inte ens en inloggning eller NOOP går ut med ett värde som inte håller.

  Scenario: Ett mappnamn med radbrytning i get_email avvisas utan att Bridge kontaktas
    When jag hämtar mejlet med UID "1" i "INBOX\r\nA1 DELETE INBOX"
    Then ska verktyget ge ett fel som nämner "Ogiltigt mailbox-namn"
    And ska Bridge inte ha fått något kommando

  Scenario: Ett UID som inte är ett tal avvisas utan att Bridge kontaktas
    When jag hämtar mejlet med UID "1:*" i "INBOX"
    Then ska verktyget ge ett fel som nämner "Ogiltigt UID"
    And ska Bridge inte ha fått något kommando

  Scenario: Ett mappnamn med radbrytning i get_mailbox_status avvisas utan att Bridge kontaktas
    When jag hämtar status för "INBOX\r\nA1 DELETE INBOX"
    Then ska verktyget ge ett fel som nämner "Ogiltigt mailbox-namn"
    And ska Bridge inte ha fått något kommando
