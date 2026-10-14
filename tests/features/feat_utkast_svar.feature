Feature: Svar och vidarebefordringar som utkast
  Som en användare som låter Claude formulera svar
  vill jag att svaret eller vidarebefordringen läggs som utkast i Drafts
  med samma mottagare, ämne och trådning som om det skickats direkt,
  så att jag kan granska det innan det går iväg.

  Background:
    Given mitt konto är "me@proton.me"
    And ett mejl i INBOX från "Anna Ek <anna@example.se>" till "me@proton.me" med kopia till "cc@example.se" och ämnet "Möte"

  Scenario: Ett svarsutkast får mottagare, Re:-ämne, trådning och citat
    When jag skapar ett svarsutkast på mejlet i INBOX med texten "Det passar bra"
    Then ska Drafts innehålla 1 utkast
    And utkastets header "To" ska innehålla "Anna Ek" med adressen "anna@example.se"
    And utkastet ska sakna headern "Cc"
    And utkastets ämne ska vara "Re: Möte"
    And utkastets header "In-Reply-To" ska vara originalets Message-ID
    And utkastets text ska innehålla "Det passar bra"
    And utkastets text ska innehålla "> Originaltext"
    And inget mejl ska ha skickats
    And svaret ska ange mappen "Drafts", utkastets UID och dess Message-ID

  Scenario: Svara alla som utkast tar med kopiemottagarna
    When jag skapar ett svara-alla-utkast på mejlet i INBOX med texten "Hej alla"
    Then utkastets header "Cc" ska innehålla "" med adressen "cc@example.se"
    And inget mejl ska ha skickats

  Scenario: Ett svarsutkast blir identiskt med det svar som reply_to_email skickar
    When jag skapar ett svarsutkast på mejlet i INBOX med texten "Det passar bra"
    And jag svarar direkt på mejlet i INBOX med texten "Det passar bra"
    Then ska utkastet och det skickade svaret ha samma mottagare, ämne, trådning och text

  Scenario: Ett vidarebefordringsutkast får Fwd:-ämne och originalet med bilagor
    Given att mejlet i INBOX har bilagan "faktura.pdf"
    When jag skapar ett vidarebefordringsutkast av mejlet i INBOX till "bob@example.com" med texten "Se nedan"
    Then utkastets header "To" ska innehålla "" med adressen "bob@example.com"
    And utkastets ämne ska vara "Fwd: Möte"
    And utkastets text ska innehålla "Se nedan"
    And utkastets text ska innehålla "Forwarded message"
    And utkastet ska ha bilagan "faktura.pdf"
    And inget mejl ska ha skickats

  Scenario: Svarsutkast på ett mejl som inte finns ger fel
    When jag skapar ett svarsutkast på UID "999" i INBOX med texten "Hej"
    Then ska anropet misslyckas med meddelandet "Inget meddelande med UID 999 i INBOX"
    And ska Drafts innehålla 0 utkast
