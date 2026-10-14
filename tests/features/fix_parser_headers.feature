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
