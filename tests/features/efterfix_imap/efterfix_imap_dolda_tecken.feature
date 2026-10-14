Feature: UID och mappnamn med dolda tecken avvisas
  Som användare av ett läsverktyg
  vill jag att ett UID eller mappnamn med en avslutande radbrytning eller
  siffror från andra skriftsystem avvisas,
  eftersom radbrytningen annars skickas rakt ut i IMAP-kommandot.

  Scenario: Ett UID med en avslutande radbrytning avvisas
    Given att mejlet med UID "123" ligger i "INBOX"
    When jag hämtar mejlet med UID "123\n" i "INBOX"
    Then ska verktyget ge ett fel som nämner "Ogiltigt UID"
    And ska Bridge inte ha fått något kommando

  Scenario: Ett UID med siffror från ett annat skriftsystem avvisas
    When jag hämtar mejlet med UID "１２３" i "INBOX"
    Then ska verktyget ge ett fel som nämner "Ogiltigt UID"
    And ska Bridge inte ha fått något kommando

  Scenario: Ett mappnamn med en avslutande radbrytning avvisas
    When jag hämtar status för "INBOX\n"
    Then ska verktyget ge ett fel som nämner "Ogiltigt mailbox-namn"
    And ska Bridge inte ha fått något kommando
