Feature: En session som slutat läsa glöms efter några tidsgränser i rad
  Som drift av MCP-servern
  vill jag att en klientsession som inte längre tar emot notiser till slut glöms
  i stället för att varje ny notis väntar ut hela tidsgränsen för den, för alltid,
  medan andra sessioner fortsätter få sina notiser.

  Scenario: En hängande session glöms efter tre tidsgränser i rad
    Given att en session som slutat läsa och en session som läser prenumererar på mappresursen för "INBOX"
    When servern meddelar att mappresursen för "INBOX" har ändrats tills den hängande sessionen nått tre tidsgränser i rad
    Then ska den hängande sessionens prenumerationer vara borttagna
    And ska det loggas att sessionen glömts
    And ska sessionen som läser fortfarande prenumerera och ha fått varje notis

  Scenario: En enstaka tidsgräns glömmer inte sessionen
    Given att en session prenumererar på mappresursen för "INBOX"
    And att notisen till den hinner ta för lång tid två gånger, sedan lyckas, och sedan tar för lång tid två gånger till
    When servern meddelar att mappresursen för "INBOX" har ändrats fem gånger
    Then ska sessionen fortfarande prenumerera på mappresursen för "INBOX"
