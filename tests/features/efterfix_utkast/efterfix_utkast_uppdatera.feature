Feature: Uppdatera svars- och vidarebefordringsutkast utan att något går förlorat
  Som en användare som låter Claude skriva om ett utkast
  vill jag att trådningen, bilagorna och de inbäddade bilderna följer med till den nya versionen
  och att den gamla versionen hamnar i papperskorgen i stället för att raderas
  så att svaret stannar i tråden och inget går förlorat om något blev fel.

  Background:
    Given mitt konto är "me@proton.me"
    And ett mejl i INBOX från "Anna <anna@example.se>" med ämnet "Offert" och bilagan "offert.pdf"

  Scenario: Ett svarsutkast stannar i tråden efter uppdateringen
    Given ett svarsutkast på mejlet i INBOX
    When jag uppdaterar utkastet till "anna@example.se" med ämnet "Re: Offert" och texten "Ny svarstext"
    Then ska det nya utkastets "In-Reply-To" vara originalets Message-ID
    And ska det nya utkastets "References" innehålla originalets Message-ID
    And utkastets text ska innehålla "Ny svarstext"
    And svaret ska ange att rubrikerna "In-Reply-To, References" behölls

  Scenario: Ett vidarebefordringsutkast behåller originalets bilaga oförändrad
    Given ett vidarebefordringsutkast av mejlet i INBOX till "bo@example.se"
    When jag uppdaterar utkastet till "bo@example.se" med ämnet "Fwd: Offert" och texten "FYI, se bilagan"
    Then utkastet ska ha bilagan "offert.pdf" med originalets innehåll
    And utkastets text ska innehålla "FYI, se bilagan"
    And svaret ska ange att bilagan "offert.pdf" behölls

  Scenario: En inbäddad bild ligger kvar bredvid HTML-versionen som visar den
    Given ett utkast i Drafts med HTML som visar den inbäddade bilden "logo.png"
    When jag uppdaterar utkastet med texten "Ny text" och HTML som visar samma bild
    Then ska bilden "logo.png" ligga i samma multipart/related som HTML-delen

  Scenario: Utan HTML-version blir den inbäddade bilden en vanlig bilaga
    Given ett utkast i Drafts med HTML som visar den inbäddade bilden "logo.png"
    When jag uppdaterar utkastet till "asa@example.se" med ämnet "Logga" och texten "Bara text nu"
    Then utkastet ska ha bilagan "logo.png"

  Scenario: Det gamla utkastet flyttas till Trash och raderas inte
    Given ett svarsutkast på mejlet i INBOX
    When jag uppdaterar utkastet till "anna@example.se" med ämnet "Re: Offert" och texten "Ny svarstext"
    Then ska Drafts innehålla 1 utkast
    And det gamla utkastet ska ligga i Trash
    And inget UID STORE eller UID EXPUNGE ska ha skickats
    And svaret ska ange att det gamla utkastet flyttades till "Trash"

  Scenario: Det gamla utkastets egen interna Proton-referens följer inte med
    Given ett utkast från Proton med det interna id:t "utkast-1" som svarar på "<orig-1@example.se>"
    When jag uppdaterar utkastet till "anna@example.se" med ämnet "Re: Offert" och texten "Ny svarstext"
    Then ska det nya utkastets "References" vara "<orig-1@example.se> <orig-pm@protonmail.internalid>"
    And ska det nya utkastets "In-Reply-To" vara "<orig-1@example.se>"
