Feature: Hämta en bilaga ur ett mejl
  Som MCP-klient som ser en bilaga i get_email
  vill jag kunna spara den i bilagekatalogen eller läsa den direkt
  så att jag kan arbeta vidare med filen utan att öppna Proton.

  Background:
    Given ett mejl med UID "42" i "INBOX" med brödtext och bilagorna "faktura.pdf" och "anteckning.txt"

  Scenario: Bilagan sparas i bilagekatalogen
    When jag hämtar bilaga 0 ur mejlet "42" i "INBOX"
    Then ska filen "faktura.pdf" finnas i bilagekatalogen med bilagans innehåll
    And ska svaret ange sökvägen, storleken, typen "application/pdf" och sha256

  Scenario: Att hämta samma bilaga två gånger skriver inte över den första filen
    When jag hämtar bilaga 0 ur mejlet "42" i "INBOX"
    And jag hämtar bilaga 0 ur mejlet "42" i "INBOX"
    Then ska filen "faktura (1).pdf" finnas i bilagekatalogen med bilagans innehåll
    And ska filen "faktura.pdf" finnas i bilagekatalogen med bilagans innehåll

  Scenario: En liten binär bilaga kan läsas direkt som base64
    When jag hämtar bilaga 0 ur mejlet "42" i "INBOX" utan att spara
    Then ska svaret innehålla bilagan base64-kodad
    And ska inget ha sparats i bilagekatalogen

  Scenario: En textbilaga läses direkt som text
    When jag hämtar bilaga 1 ur mejlet "42" i "INBOX" utan att spara
    Then ska svaret innehålla texten "Räksmörgås på fredag"

  Scenario: En bilaga över gränsen kan inte läsas direkt
    Given att gränsen för direktläsning är 4 byte
    When jag hämtar bilaga 0 ur mejlet "42" i "INBOX" utan att spara
    Then ska hämtningen avvisas med ett fel som nämner "save=True"

  Scenario: Ett avsändarstyrt filnamn med sökväg kan inte skriva utanför katalogen
    Given ett mejl med UID "7" i "INBOX" med en bilaga som heter "../../../.zshrc"
    When jag hämtar bilaga 0 ur mejlet "7" i "INBOX"
    Then ska filen "zshrc" finnas i bilagekatalogen med bilagans innehåll
    And ska inget ha skrivits utanför bilagekatalogen

  Scenario: Ett index utanför listan ger ett begripligt fel
    When jag hämtar bilaga 5 ur mejlet "42" i "INBOX"
    Then ska hämtningen avvisas med ett fel som nämner "2 bilagor"

  Scenario: Ett UID som inte finns i mappen ger ett begripligt fel
    When jag hämtar bilaga 0 ur mejlet "99" i "INBOX"
    Then ska hämtningen avvisas med ett fel som nämner "Inget meddelande med UID 99"
