Feature: En session som kopplar ner glöms direkt
  Som drift av MCP-servern
  vill jag att prenumerationerna för en klient som kopplat ner tas bort när sessionen stängs
  och inte först när nästa notis till den misslyckas
  eftersom en server som körs länge annars samlar på sig döda sessioner.

  Scenario: Registret är tomt innan någon notis har skickats
    Given att en riktig klientsession prenumererar på "mailbox://INBOX" och "email://INBOX/42"
    When klienten kopplar ner
    Then ska ingen session finnas kvar i prenumerationsregistret
    And ska ingen notis ha skickats
