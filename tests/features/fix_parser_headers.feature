Feature: Tålig avkodning av rubriker i inkommande mejl
  Som en MCP-klient
  vill jag att konstigt kodade rubriker avkodas till läsbar text
  så att ett enda mejl aldrig kan stoppa läsning eller listning av inkorgen.

  Scenario: Ämne med okänd teckenkodning i ett kodat ord
    Given ett mejl med rubrikraden "Subject: =?x-unknown?Q?hej?="
    When jag hämtar mejlet med get_email
    Then ska ämnet vara "hej"

  Scenario: Ämne med språktagg i det kodade ordet (RFC 2231)
    Given ett mejl med rubrikraden "Subject: =?utf-8*sv?Q?=C3=A5r?="
    When jag hämtar mejlet med get_email
    Then ska ämnet vara "år"

  Scenario: Listningen överlever ett mejl med okänd teckenkodning
    Given en IMAP-sida med tre mejl där det mittersta har ämnet "=?x-unknown?Q?boom?="
    When sidans metadata parsas
    Then ska 3 mejl listas
    And det mittersta mejlets ämne ska vara "boom"

  Scenario: Rå UTF-8 i rubrikerna (RFC 6532)
    Given ett mejl med råa UTF-8-rubriker från "Åsa Öberg <asa@x.se>" med ämnet "SV: möte"
    When jag hämtar mejlet med get_email
    Then ska ämnet vara "SV: möte"
    And avsändaren ska vara "Åsa Öberg <asa@x.se>"
    And alla fält ska gå att serialisera som JSON

  Scenario: Listningen visar rå UTF-8 i ämnet
    Given en IMAP-sida med tre mejl där det mittersta har ämnet "Hälsningar från Göteborg"
    When sidans metadata parsas
    Then det mittersta mejlets ämne ska vara "Hälsningar från Göteborg"

  Scenario: Kodade namn i To och Cc avkodas
    Given ett mejl med rubrikraden "To: =?utf-8?q?Gr=C3=B6n?= <g@x.se>, =?utf-8?b?w4VzYQ==?= <asa@x.se>"
    When jag hämtar mejlet med get_email
    Then ska mottagarna vara "Grön <g@x.se>" och "Åsa <asa@x.se>"

  Scenario: Svar till en avsändare med kommatecken i det kodade namnet
    Given ett mejl från "=?utf-8?q?=C3=96berg=2C_=C3=85sa?= <asa@x.se>" i INBOX
    When jag svarar på mejlet med reply_to_email
    Then ska svaret skickas till adressen "asa@x.se"
    And mottagaren ska godkännas av SMTP-klientens adresskontroll
