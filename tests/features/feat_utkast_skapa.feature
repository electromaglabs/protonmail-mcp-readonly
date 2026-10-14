Feature: Skapa utkast i stället för att skicka direkt
  Som en användare som låter Claude skriva mejl
  vill jag att Claude kan lägga mejlet som ett utkast i Drafts
  så att jag kan granska det i Proton innan något skickas.

  Background:
    Given mitt konto är "me@proton.me"

  Scenario: Ett nytt utkast hamnar i Drafts och skickas inte
    When jag skapar ett utkast till "Åsa Öberg <asa@example.se>" med ämnet "Offert" och texten "Hej Åsa"
    Then ska Drafts innehålla 1 utkast
    And utkastet ska ha flaggorna "\Draft \Seen"
    And utkastets header "To" ska innehålla "Åsa Öberg" med adressen "asa@example.se"
    And utkastets ämne ska vara "Offert"
    And utkastets text ska innehålla "Hej Åsa"
    And inget mejl ska ha skickats
    And svaret ska ange mappen "Drafts", utkastets UID och dess Message-ID

  Scenario: Hemlig kopia sparas i utkastet så att den syns vid granskningen
    When jag skapar ett utkast till "bob@example.com" med hemlig kopia till "hemlig@example.se"
    Then utkastets header "Bcc" ska innehålla "" med adressen "hemlig@example.se"
    And inget mejl ska ha skickats

  Scenario: UID:t hittas via Message-ID när Bridge inte svarar med APPENDUID
    Given att Bridge inte svarar med APPENDUID
    When jag skapar ett utkast till "Åsa Öberg <asa@example.se>" med ämnet "Offert" och texten "Hej Åsa"
    Then svaret ska ange mappen "Drafts", utkastets UID och dess Message-ID

  Scenario: En ogiltig adress ger fel och inget utkast skapas
    When jag skapar ett utkast till "inte-en-adress" med ämnet "Offert" och texten "Hej"
    Then ska anropet misslyckas med meddelandet "Ogiltig e-postadress"
    And ska Drafts innehålla 0 utkast

  Scenario: Bridge vägrar spara utkastet
    Given att Bridge svarar NO på "APPEND"
    When jag skapar ett utkast till "asa@example.se" med ämnet "Offert" och texten "Hej"
    Then ska anropet misslyckas med meddelandet "Sparandet av utkastet i Drafts misslyckades"
    And ska Drafts innehålla 0 utkast
