 grep -rl 's3:\/\/pymegsdk-data' ./ | xargs sed -i "s/s3:\/\/pymegsdk-data/s3:\/\/gaoxiang/g"  
