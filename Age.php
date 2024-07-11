<?php
$YY = date('Y / ');
$MM = date('m / ');
$DD = date('d / ');
if(isset($_POST['submit']))
{
  $y = $_POST['y'];
  $m = $_POST['m'];
  $d = $_POST['d'];
  $ye = $YY - $y;
  $me = $MM - $m;
  $de = $DD - $d;
  
  if($ye <= 20)
  {
    $j = "عادك جاهل";
  }
  else if($ye <= 30)
  {
    $j = "عادك شباب";
  }
  else if($ye >= 31)
  {
    $j = "قدك شيبة ( عجوز )";
  }
}
?>
<html>
  <head>
    <style>
body
{
  background-color: #58585d;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
form
{
  background-color: #c1c1c8;
  padding: 10px 20px;
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  
  text-align: center;
}
input
{
  margin-bottom: 10px;
  border-radius: 5px;
  border: none;
}
::placeholder
{
  text-align: center;
}

    </style>
  </head>
  <body>
    <form method="post">
      <p> احسب عمرك </p>  
      <input type="text" placeholder="السنة" name="y">
      <input type="text" placeholder="الشهر" name="m">
      <input type="text" placeholder="اليوم" name="d">
      <input type="submit" name="submit">
      <p>
        <?php
        echo $j;
        echo "<br>";
        echo $ye , ' - ' , $me , ' - ' , $de; 
        
        ?>
      </p>
    </form>
  </body>
</html>
