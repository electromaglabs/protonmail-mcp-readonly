Feature: Uppdatera ett utkast
  Som en användare som granskar Claudes utkast
  vill jag kunna be Claude ändra ett utkast
  så att Drafts innehåller den nya versionen och inte båda.

  Background:
    Given mitt konto är "me@proton.me"
    And ett utkast i Drafts till "asa@example.se" med ämnet "Offert" och texten "Första versionen"

  Scenario: Utkastet ersätts av den nya versionen
    When jag uppdaterar utkastet till "asa@example.se" med ämnet "Offert v2" och texten "Andra versionen"
    Then ska Drafts innehålla 1 utkast
    And utkastets ämne ska vara "Offert v2"
    And utkastets text ska innehålla "Andra versionen"
    And det gamla utkastet ska ha flyttats till Trash med UID MOVE på sitt UID
    And inget mejl ska ha skickats
    And svaret ska ange mappen "Drafts", utkastets UID och dess Message-ID

  Scenario: Misslyckas sparandet ligger det gamla utkastet kvar orört
    Given att Bridge svarar NO på "APPEND"
    When jag uppdaterar utkastet till "asa@example.se" med ämnet "Offert v2" och texten "Andra versionen"
    Then ska anropet misslyckas med meddelandet "Sparandet av utkastet i Drafts misslyckades"
    And ska Drafts innehålla 1 utkast
    And utkastets ämne ska vara "Offert"
    And inget UID STORE eller UID EXPUNGE ska ha skickats

  Scenario: Ett utkast som inte finns kan inte uppdateras
    When jag uppdaterar utkastet med UID "999" till "asa@example.se" med ämnet "x" och texten "y"
    Then ska anropet misslyckas med meddelandet "Inget meddelande med UID 999 i Drafts"
    And ska Drafts innehålla 1 utkast
    And inget APPEND ska ha skickats

  Scenario: En ogiltig adress ändrar ingenting
    When jag uppdaterar utkastet till "inte-en-adress" med ämnet "Offert v2" och texten "Andra versionen"
    Then ska anropet misslyckas med meddelandet "Ogiltig e-postadress"
    And utkastets ämne ska vara "Offert"
    And inget APPEND ska ha skickats
