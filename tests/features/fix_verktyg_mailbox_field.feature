Feature: Svaren talar om vilken mapp ett UID hör till
  Som en MCP-klient
  vill jag att varje brev i svaren anger sin mapp
  eftersom ett UID bara är unikt inom en mapp och samma nummer i INBOX är ett annat brev.

  Scenario: Brev listade i en etikett anger etiketten som mapp
    Given att etiketten "Labels/Kvitto" innehåller brevet med UID "14"
    When jag listar brev i "Labels/Kvitto"
    Then ska varje brev i listan ha mailbox "Labels/Kvitto"
    And svaret ska ange mailbox "Labels/Kvitto"

  Scenario: Sökträffar anger mappen de hittades i
    Given att sökning i "Starred" ger brevet med UID "14"
    When jag söker brev i "Starred"
    Then ska varje sökträff ha mailbox "Starred"

  Scenario: Ett hämtat brev anger sin mapp
    Given att brevet med UID "14" finns i "Archive"
    When jag hämtar brevet med UID "14" ur "Archive"
    Then ska brevet ha mailbox "Archive"
