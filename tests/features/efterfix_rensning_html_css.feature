Feature: Inline-stilar tolkas som i en webbläsare
  Som användare av en LLM som läser min e-post
  vill jag att dubbla deklarationer och CSS-kommentarer tolkas som e-postklienten gör
  så att text som är gömd för mig också är gömd för modellen, och synlig text syns.

  Scenario Outline: Gömmande stil som bara en webbläsare förstår
    Given ett HTML-mejl med "Hej" och ett element med stilen "<stil>" som innehåller "SECRET"
    When jag hämtar mejlet som text med get_email
    Then ska brödtexten vara "Hej"

    Examples:
      | stil                                  |
      | font-size:14px;font-size:0            |
      | visibility:visible;visibility:hidden  |
      | opacity:1;opacity:0                   |
      | display:/**/none                      |

  Scenario: Synlig text göms inte av en tidigare deklaration
    Given ett HTML-mejl med "Hej" och ett element med stilen "font-size:0;font-size:14px" som innehåller "SYNLIG"
    When jag hämtar mejlet som text med get_email
    Then ska brödtexten vara "Hej\n\nSYNLIG"
