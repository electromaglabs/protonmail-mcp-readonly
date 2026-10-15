Feature: Bridge-lösenordet maskeras i fel även i omskriven eller kapad form
  Som användare som låter en LLM läsa felmeddelandena
  vill jag att Bridge-lösenordet aldrig syns i ett fel
  även om det står URL-kodat, med hopslagna blanksteg eller kapat.

  Scenario Outline: Lösenordet maskeras i felet till modellen
    Given Bridge-lösenordet är "<lösenord>"
    When ett verktyg får ett anslutningsfel vars text innehåller lösenordet <form>
    Then ska felet till modellen inte innehålla någon del av lösenordet

    Examples:
      | lösenord                  | form                                 |
      | hemligt  lösen/ord+1      | URL-kodat                            |
      | hemligt  lösen/ord+1      | med hopslagna blanksteg              |
      | hemligt-losenord-123      | sist i en text som kapas mitt i det  |
