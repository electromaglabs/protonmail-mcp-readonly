Feature: Bilagor i ett mejl har index och kan plockas ut
  Som MCP-klient som läser ett mejl med get_email
  vill jag att varje bilaga har ett index och en stabil identifierare
  så att jag kan hämta exakt den bilaga jag ser i listan.

  Scenario: Varje bilaga får ett index och ett MIME-delnummer
    Given ett mejl med brödtext och bilagorna "a.pdf" och "b.png"
    When mejlet parsas
    Then ska bilagorna ha indexen 0, 1
    And ska bilagan med index 0 ha delnumret "2"
    And ska bilagan med index 1 ha delnumret "3"

  Scenario: Bilagans innehåll plockas ut med samma index som i listan
    Given ett mejl med brödtext och bilagorna "a.pdf" och "b.png"
    When bilaga 1 plockas ut ur det råa mejlet
    Then ska den utplockade bilagan heta "b.png" med typen "image/png"
    And ska innehållet vara bilagans ursprungliga bytes
    And ska storleken stämma med listan i get_email

  Scenario: Ett bifogat mejl plockas ut som hela meddelandet
    Given ett mejl med ett bifogat mejl med ämnet "Inre"
    When bilaga 0 plockas ut ur det råa mejlet
    Then ska den utplockade bilagan ha typen "message/rfc822"
    And ska innehållet vara ett mejl med ämnet "Inre"
    And ska storleken stämma med listan i get_email

  Scenario: Ett index utanför listan ger ett fel som anger antalet bilagor
    Given ett mejl med brödtext och bilagorna "a.pdf" och "b.png"
    When bilaga 2 plockas ut ur det råa mejlet
    Then ska utplockningen avvisas med ett fel som nämner "2 bilagor"
