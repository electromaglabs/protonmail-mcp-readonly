Feature: MCP-kontraktet är detsamma efter byte av MCP-SDK
  Som den som byter MCP-SDK (mcp 1.x → 2.x)
  vill jag att allt en klient ser av servern jämförs mot en sparad facitfil
  eftersom ett SDK-byte kan ändra scheman, fel och förmågor utan att något test om
  enskilda verktyg märker det — och modellen bygger sina anrop på just det den ser.

  Scenario: Det klienten ser vid anslutning är oförändrat
    When en MCP-klient ansluter och listar verktyg, resurser, resursmallar och promptar
    Then ska serverInfo, instruktionerna och förmågorna vara som i facitfilen
    And ska verktygens namn, titlar, scheman och annoteringar vara som i facitfilen
    And ska resurserna, resursmallarna och promptarna vara som i facitfilen

  Scenario: Felen modellen ser är oförändrade
    When en MCP-klient gör anrop som ger fel
    Then ska felen vara som i facitfilen
    And ska serverns egna felmeddelanden nå klienten i sin helhet
    And ska inget resursfel ha ett engelskt prefix från SDK:n

  Scenario: Ett verktyg som policyn vägrar ger den svenska vägran
    Given servern är skrivskyddad
    When en MCP-klient anropar "send_email"
    Then ska anropet ge ett fel som nämner "skrivskydd"
    And ska felet inte börja med "Error executing tool"
