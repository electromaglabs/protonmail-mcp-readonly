Feature: Serverfel vid listning och hämtning syns som fel
  Som en MCP-klient
  vill jag få veta när Bridge nekar en listning eller hämtning, med Bridges förklaring,
  så att jag inte tror att brevlådan är tom eller att ett mejl inte finns.

  Scenario: Bridge nekar LIST
    Given att Bridge nekar LIST med "sync in progress"
    When jag listar mapparna
    Then ska verktyget ge ett fel som nämner "sync in progress"

  Scenario: Bridge nekar FETCH när en sida listas
    Given att mejlet med UID "3" ligger i "INBOX"
    And att Bridge nekar FETCH med "backend unavailable"
    When jag listar mejlen i "INBOX"
    Then ska verktyget ge ett fel som nämner "backend unavailable"

  Scenario: Bridge nekar hämtningen av ett mejl som finns
    Given att mejlet med UID "4" ligger i "INBOX"
    And att Bridge nekar FETCH med "failed to build message"
    When jag hämtar mejlet med UID "4" i "INBOX"
    Then ska verktyget ge ett fel som nämner "failed to build message"
    And ska felet inte påstå att mejlet saknas

  Scenario: Bridge nekar hämtningen av rubrikerna
    Given att mejlet med UID "4" ligger i "INBOX"
    And att Bridge nekar FETCH med "failed to build message"
    When jag hämtar rubrikerna för UID "4" i "INBOX"
    Then ska verktyget ge ett fel som nämner "failed to build message"
    And ska felet inte påstå att mejlet saknas

  Scenario: Ett UID som inte finns ger fortfarande "Inget meddelande"
    Given att mejlet med UID "4" ligger i "INBOX"
    When jag hämtar mejlet med UID "5" i "INBOX"
    Then ska verktyget ge ett fel som nämner "Inget meddelande med UID 5"
